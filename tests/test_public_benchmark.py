"""Public-benchmark interface contract; fixtures here are only test simulations."""
import json
import zipfile
from pathlib import Path
import pytest
from benchmarks.public_defects import evaluate


def test_offline_manifest_evaluator_and_unavailable_semantic(tmp_path: Path):
    with zipfile.ZipFile(tmp_path / 'fixture.zip', 'w') as archive:
        archive.writestr('calculator.py', 'def add(a,b):\n return a-b\n')
        archive.writestr('other.py', 'def difference(a,b):\n return a-b\n')
    row = {'id': 'test-case', 'source_url': 'https://github.com/org/project', 'revision': 'a'*40,
           'split': 'test', 'issue': 'The add function subtracts instead of addition.',
           'archive': 'fixture.zip', 'fault_files': ['calculator.py']}
    manifest = tmp_path / 'cases.jsonl'
    manifest.write_text(json.dumps(row) + '\n')
    result = evaluate(manifest, tmp_path / 'out')
    assert result['cases'] == 1
    assert result['strategies']['lexical']['status'] == 'measured'
    assert result['strategies']['semantic']['status'] == 'incomplete'
    assert len(json.loads((tmp_path / 'out/per_case.json').read_text())) == 4


def test_benchmark_rejects_path_escape_and_training_cases(tmp_path: Path):
    with zipfile.ZipFile(tmp_path / 'fixture.zip', 'w') as archive:
        archive.writestr('a.py', 'x=1')
    row = {'id': 'test-case', 'source_url': 'https://github.com/org/project', 'revision': 'a'*40,
           'split': 'train', 'issue': 'The function returns an incorrect result.',
           'archive': '../fixture.zip', 'fault_files': ['a.py']}
    manifest = tmp_path / 'cases.jsonl'
    manifest.write_text(json.dumps(row))
    with pytest.raises(ValueError): evaluate(manifest, tmp_path / 'out')
