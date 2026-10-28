"""Honest, Docker-isolated end-to-end repair trials on supplied pinned defect snapshots.

Accepts the SAME provenance-validated held-out manifest as public_defects.py.
Every case must have a failing baseline test suite: a successful candidate must
make that suite pass. No reference fix is loaded or sent to the language model.

Real model inference and real Docker tests are mandatory for *measured* outcomes.
Provider unavailability is a recorded failed/unavailable attempt, never success.
"""
from __future__ import annotations

import argparse
import hashlib
from collections import Counter
import json
import shutil
import statistics
import tempfile
import time
from pathlib import Path

from benchmarks.public_defects import _case
from packages.ingest import extract_archive, MAX_ZIP
from packages.intelligence import index_repository
from packages.repair import candidate_diff, ollama_candidates
from packages.retrieval import rank
from packages.verification import verify, _validate_source_budget


def _clone_copy(source: Path, destination: Path) -> None:
    """No links are followed, including links inside a supported repository."""
    problem = _validate_source_budget(source)
    if problem:
        raise ValueError(problem)
    shutil.copytree(source, destination, symlinks=True,
                    ignore=shutil.ignore_patterns('.git', '.env', '.venv', 'node_modules', '__pycache__'))
    for item in destination.rglob('*'):
        if item.is_symlink():
            item.unlink()


def evaluate(manifest: Path, output: Path, *, method: str = 'lexical', attempts: int = 2) -> dict:
    if method not in {'lexical', 'semantic', 'hybrid'} or not 1 <= attempts <= 3:
        raise ValueError('invalid evaluation configuration')
    if not manifest.is_file() or manifest.stat().st_size > 2_000_000:
        raise ValueError('missing or oversized manifest')
    rows = [json.loads(line) for line in manifest.read_text('utf-8').splitlines() if line.strip()]
    if not 1 <= len(rows) <= 100:
        raise ValueError('trial manifest requires 1..100 cases')
    ids = [row.get('id') for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate trial IDs')
    checked = [(_case(row, manifest.parent), row) for row in rows]
    per_case = []
    for (archive, gold), row in checked:
        started = time.monotonic()
        result = {'id': row['id'], 'source_url': row['source_url'], 'revision': row['revision'],
                  'method': method, 'status': 'unavailable', 'resolved': False,
                  'model_attempts': None, 'configured_attempt_budget': attempts, 'patches_valid': 0, 'patches_applied': 0,
                  'failed_attempts': [], 'baseline_test_status': 'not_run'}
        with tempfile.TemporaryDirectory(prefix='patchproof-repair-evaluation-') as scratch:
            source_root = Path(scratch) / 'original'
            if archive.stat().st_size > MAX_ZIP:
                raise ValueError(f"{row['id']}: archive exceeds import budget")
            extract_archive(archive.read_bytes(), source_root)
            entries = index_repository(source_root)
            if not gold.intersection({e['path'] for e in entries}):
                raise ValueError(f"{row['id']}: no labeled defective file in indexed snapshot")
            # Only Python/Node bare test fixtures can be verified by the fixed Docker runners.
            runtime = ('python' if all(path.endswith('.py') for path in gold) else
                       'node' if all(path.endswith('.js') for path in gold) else None)
            if runtime is None:
                result['status'] = 'unsupported_language'
                result['failure_category'] = 'unsupported_test_runtime'
            else:
                baseline = verify(source_root, runtime=runtime, timeout=30)
                result['baseline_test_status'] = baseline['status']
                if baseline['status'] != 'failed':
                    result['status'] = 'invalid_baseline' if baseline['status'] == 'passed' else 'unavailable'
                    result['failure_category'] = 'not_reproducibly_failing' if baseline['status'] == 'passed' else 'sandbox_unavailable'
                else:
                    try:
                        locations = rank(entries, row['issue'], method, limit=10)
                        indexed = {entry['path']: entry for entry in entries}
                        scope = [indexed[r['path']] for r in locations[:5]]
                        usage: dict = {}
                        proposals, model = ollama_candidates(row['issue'], scope, attempts=attempts, usage_sink=usage.update)
                        result['model'] = model
                        result['model_usage'] = usage
                        result['model_attempts'] = usage.get('generation_requests')
                        result['candidate_count'] = len(proposals)
                        result['status'] = 'attempted'
                        seen = set()
                        for index, proposal in enumerate(proposals):
                            ident = (proposal.path, proposal.old, proposal.new)
                            if ident in seen:
                                continue
                            seen.add(ident)
                            if proposal.path not in gold and proposal.path not in {r['path'] for r in locations[:10]}:
                                result['failed_attempts'].append('outside_localization_scope')
                                continue
                            try:
                                original, updated, diff = candidate_diff(source_root, proposal,
                                                                          {r['path'] for r in locations[:10]})
                            except (ValueError, SyntaxError, UnicodeError) as exc:
                                result['failed_attempts'].append('invalid_patch_' + type(exc).__name__)
                                continue
                            result['patches_valid'] += 1
                            patched = Path(scratch) / f'patched-{index}'
                            _clone_copy(source_root, patched)
                            target = patched / proposal.path
                            if target.read_text('utf-8') != original:
                                result['failed_attempts'].append('artifact_changed')
                                continue
                            target.write_text(updated, encoding='utf-8')
                            result['patches_applied'] += 1
                            evidence = verify(patched, runtime=runtime, timeout=30)
                            if evidence['status'] == 'passed':
                                result['resolved'] = True
                                result['status'] = 'tests_passed_only'
                                result['selected_candidate_index'] = index
                                result['selected_diff_sha256'] = hashlib.sha256(diff.encode()).hexdigest()
                                break
                            result['failed_attempts'].append('sandbox_' + evidence['status'])
                        if not result['resolved']:
                            result['status'] = 'not_resolved'
                    except Exception as exc:
                        result['status'] = 'unavailable'
                        result['failure_category'] = type(exc).__name__
                        result['failure_reason'] = str(exc)[:300]
        result['duration_ms'] = round((time.monotonic() - started) * 1000, 1)
        per_case.append(result)

    attempted = [r for r in per_case if r['baseline_test_status'] == 'failed' and r['status'] in {'attempted', 'not_resolved', 'tests_passed_only'}]
    complete = len(attempted) == len(rows)
    # Denominators are deliberately all supplied cases; an unavailable provider
    # does not silently disappear from a success-rate denominator.
    valid = sum(r['patches_valid'] for r in attempted)
    applied = sum(r['patches_applied'] for r in attempted)
    proposed = sum(r.get('candidate_count', 0) for r in attempted)
    failure_categories = dict(sorted(Counter(r.get('failure_category', r['status'])
                                     for r in per_case if not r['resolved']).items()))
    summary = {
        'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
        'method': method, 'case_count': len(rows), 'measured_cases': len(attempted),
        'status': 'measured' if complete else 'incomplete',
        'end_to_end_test_resolution_rate': (sum(r['resolved'] for r in attempted) / len(attempted)) if complete else None,
        'candidate_patch_validity_rate': (valid / proposed if proposed else None) if complete else None,
        'patch_application_success_rate': (applied / valid if valid else None) if complete else None,
        'candidate_count': proposed if complete else None,
        'patches_valid': valid if complete else None,
        'patches_applied': applied if complete else None,
        'failure_categories': failure_categories,
        'median_duration_ms': (statistics.median(r['duration_ms'] for r in attempted)) if complete else None,
        'claims': 'Test-suite resolution only; this is not formal correctness or a verified production fix.',
        'warning': 'Missing providers, tests and failed repairs are included; never exclude unavailable cases from denominator.',
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / 'per_case.json').write_text(json.dumps(per_case, indent=2) + '\n', encoding='utf-8')
    (output / 'aggregate.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--method', choices=('lexical', 'semantic', 'hybrid'), default='lexical')
    parser.add_argument('--attempts', type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.manifest, args.output, method=args.method, attempts=args.attempts), indent=2))
