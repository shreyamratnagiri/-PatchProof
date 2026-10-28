"""Offline evaluator for independently sourced real-repository defect snapshots.

No repository code is executed and reference patches are never sent to a model.
Every row requires a traceable upstream URL and pinned revision. This tool
measures localization only; it must not be misreported as repair success.

Usage:
 python -m benchmarks.public_defects --manifest /path/to/public_cases.jsonl --output /path/to/results

A manifest row contains: id, source_url, revision (40 hex chars), split (test),
issue, archive (relative path to a local ZIP snapshot), fault_files (nonempty
array of repository-relative paths). Test snapshots should be obtained from
known upstream historical revisions, not synthesized as claimed real defects.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from packages.ingest import MAX_ZIP, extract_archive
from packages.intelligence import index_repository
from packages.retrieval import rank

STRATEGIES = ('lexical', 'semantic', 'hybrid_no_graph', 'hybrid_graph')


def _case(row: dict, root: Path) -> tuple[Path, set[str]]:
    expected = {'id', 'source_url', 'revision', 'split', 'issue', 'archive', 'fault_files'}
    if set(row) != expected:
        raise ValueError('manifest must provide exactly the documented case fields')
    if not isinstance(row['id'], str) or not re.fullmatch(r'[\w.-]{1,100}', row['id']):
        raise ValueError('invalid case identifier')
    url = urlparse(row['source_url'])
    if url.scheme != 'https' or url.hostname != 'github.com' or not url.path.startswith('/'):
        raise ValueError('source_url must identify an upstream GitHub repository')
    if not re.fullmatch(r'[0-9a-f]{40}', row['revision']):
        raise ValueError('revision must be pinned to a full git SHA-1')
    if row['split'] != 'test':
        raise ValueError('evaluator accepts held-out test cases only')
    if not isinstance(row['issue'], str) or not 10 <= len(row['issue']) <= 10_000:
        raise ValueError('issue description is missing or oversized')
    if not isinstance(row['fault_files'], list) or not row['fault_files']:
        raise ValueError('fault_files must be a nonempty list')
    paths = set()
    for name in row['fault_files']:
        if not isinstance(name, str):
            raise ValueError('invalid fault file')
        value = PurePosixPath(name)
        if value.is_absolute() or any(part in {'.', '..'} for part in value.parts) or '\\' in name:
            raise ValueError('unsafe fault file path')
        paths.add(value.as_posix())
    archive_name = row['archive']
    if not isinstance(archive_name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,150}\.zip', archive_name):
        raise ValueError('archive must be a local snapshot filename with no subdirectories')
    archive = (root / archive_name).resolve()
    if archive.parent != root.resolve() or archive.is_symlink() or not archive.is_file():
        raise ValueError('snapshot archive unavailable or unsafe')
    return archive, paths


def evaluate(manifest: Path, output: Path) -> dict:
    if manifest.stat().st_size > 2_000_000:
        raise ValueError('case manifest exceeds 2 MB')
    rows = [json.loads(line) for line in manifest.read_text('utf-8').splitlines() if line.strip()]
    if not 1 <= len(rows) <= 1000:
        raise ValueError('manifest requires between 1 and 1000 cases')
    ids = [row['id'] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate case identifiers')
    checked = [(_case(row, manifest.parent), row) for row in rows]
    per_case = []
    tracemalloc.start()
    for (archive, gold), row in checked:
        with tempfile.TemporaryDirectory(prefix='patchproof-public-benchmark-') as temporary:
            target = Path(temporary) / 'repository'
            if archive.stat().st_size > MAX_ZIP:
                raise ValueError(f"{row['id']}: archive exceeds upload budget")
            extract_archive(archive.read_bytes(), target)
            entries = index_repository(target)
            if not gold.intersection({e['path'] for e in entries}):
                raise ValueError(f"{row['id']}: no labeled fault file is indexed")
            for strategy in STRATEGIES:
                started = time.perf_counter()
                try:
                    results = rank(entries, row['issue'], method='hybrid' if strategy.startswith('hybrid') else strategy,
                                   use_graph=strategy == 'hybrid_graph', limit=min(len(entries), 3000))
                    rank_position = next((i for i, value in enumerate(results, 1) if value['path'] in gold), None)
                    per_case.append({'case_id': row['id'], 'strategy': strategy, 'status': 'measured',
                                     'rank': rank_position, 'recall_at_1': int(rank_position == 1),
                                     'recall_at_5': int(rank_position is not None and rank_position <= 5),
                                     'reciprocal_rank': (1 / rank_position if rank_position else 0),
                                     'latency_ms': round(1000 * (time.perf_counter() - started), 3)})
                except Exception as exc:
                    per_case.append({'case_id': row['id'], 'strategy': strategy, 'status': 'unavailable',
                                     'reason': type(exc).__name__ + ': ' + str(exc)[:240]})
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    summary: dict = {'benchmark': 'External, provenance-required, held-out localization snapshots',
                     'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
                     'cases': len(rows), 'strategies': {}, 'peak_tracemalloc_bytes': peak,
                     'limitations': ['Ground truth supplied by operator; provenance must be independently reviewed.',
                                     'No repository code executed.', 'No model patch generation or repair success measured.',
                                     'tracemalloc excludes native and total RSS memory.']}
    for strategy in STRATEGIES:
        subset = [r for r in per_case if r['strategy'] == strategy]
        measured = [r for r in subset if r['status'] == 'measured']
        if len(measured) != len(rows):
            summary['strategies'][strategy] = {'status': 'incomplete', 'measured': len(measured), 'total': len(rows)}
        else:
            durations = sorted(r['latency_ms'] for r in measured)
            summary['strategies'][strategy] = {
                'status': 'measured', 'recall_at_1': statistics.mean(r['recall_at_1'] for r in measured),
                'recall_at_5': statistics.mean(r['recall_at_5'] for r in measured),
                'mrr': statistics.mean(r['reciprocal_rank'] for r in measured),
                'median_latency_ms': statistics.median(durations),
                'p95_latency_ms': durations[max(0, math.ceil(.95 * len(durations)) - 1)],
            }
    output.mkdir(parents=True, exist_ok=True)
    (output / 'per_case.json').write_text(json.dumps(per_case, indent=2) + '\n')
    (output / 'aggregate.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.manifest, args.output), indent=2))
