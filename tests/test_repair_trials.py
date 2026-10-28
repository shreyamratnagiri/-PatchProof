"""Honest result classification; no fake model outputs are used as benchmark evidence."""
import io
import json
import zipfile
from pathlib import Path
from benchmarks import repair_trials


def _manifest(tmp_path: Path) -> Path:
    archive = tmp_path / 'snapshot.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('arithmetic.py', 'def add(x, y): return x-y\n')
        output.writestr('tests/test_arithmetic.py', 'import unittest\n')
    row = {'id':'case1', 'source_url':'https://github.com/example/benchmark',
           'revision':'a'*40, 'split':'test', 'issue':'The add method subtracts rather than adding values',
           'archive':'snapshot.zip', 'fault_files':['arithmetic.py']}
    manifest = tmp_path / 'cases.jsonl'
    manifest.write_text(json.dumps(row)+'\n')
    return manifest


def test_repair_benchmark_never_claims_success_without_sandbox(tmp_path: Path, monkeypatch):
    manifest = _manifest(tmp_path)
    called = []
    monkeypatch.setattr(repair_trials, 'verify', lambda *args, **kwargs: {'status': 'unavailable', 'verification':'unproven'})
    monkeypatch.setattr(repair_trials, 'ollama_candidates', lambda *args, **kwargs: called.append(True))
    summary = repair_trials.evaluate(manifest, tmp_path / 'results')
    assert summary['status'] == 'incomplete'
    assert summary['end_to_end_test_resolution_rate'] is None
    assert summary['measured_cases'] == 0
    assert summary['candidate_patch_validity_rate'] is None
    assert summary['patch_application_success_rate'] is None
    assert summary['failure_categories']['sandbox_unavailable'] == 1
    assert not called
    per_case = json.loads((tmp_path / 'results' / 'per_case.json').read_text())
    assert per_case[0]['status'] == 'unavailable'
    assert per_case[0]['failure_category'] == 'sandbox_unavailable'


def test_repair_benchmark_rejects_non_held_out_cases(tmp_path: Path):
    manifest = _manifest(tmp_path)
    case = json.loads(manifest.read_text())
    case['split'] = 'train'
    manifest.write_text(json.dumps(case)+'\n')
    import pytest
    with pytest.raises(ValueError, match='held-out'):
        repair_trials.evaluate(manifest, tmp_path / 'results')
