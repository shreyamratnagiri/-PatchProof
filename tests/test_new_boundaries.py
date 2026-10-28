"""Regression tests for failure modes found during the release audit.

Provider fixtures here test data validation only; they are not real neural inference.
"""
from pathlib import Path

import pytest
from packages import intelligence
from packages.ingest import safe_path
from packages.retrieval import rank


def _entries():
    return [
        {'path':'a.py','symbols':[], 'source':'add two numbers', 'imports':[], 'language':'python'},
        {'path':'b.py','symbols':[], 'source':'subtract two numbers', 'imports':[], 'language':'python'},
    ]


@pytest.mark.parametrize('answer', [[], [[1.0]], [[1.0], [1.0], [1.0]]])
def test_semantic_rejects_partial_or_extra_embedding_batches(answer):
    def broken(texts):
        if len(texts) == 2:
            return answer
        return [[1.0, 0.0]]
    with pytest.raises(ValueError, match='incorrect document count|invalid embedding'):
        rank(_entries(), 'addition problem', 'semantic', embed=broken)


def test_semantic_rejects_missing_query_embedding():
    def broken(texts):
        return [[1.0, 0.0] for _ in texts] if len(texts)>1 else []
    with pytest.raises(ValueError, match='incorrect query count'):
        rank(_entries(), 'addition problem', 'hybrid', embed=broken)


def test_semantic_rejects_batched_dimension_mismatch():
    def broken(texts):
        return [[1.0, 0.0] if 'add' in text else [1.0] for text in texts]
    with pytest.raises(ValueError, match='dimensions'):
        rank(_entries(), 'addition problem', 'hybrid', embed=broken)


def test_many_empty_directories_cannot_force_unbounded_walk(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(intelligence, 'MAX_DIRECTORIES', 3)
    for n in range(8):
        (tmp_path / f'{n:02}').mkdir()
    (tmp_path / '07' / 'surprise.py').write_text('x = 3')
    assert intelligence.index_repository(tmp_path) == []


@pytest.mark.parametrize('relative', ['x//file.py', 'x/./file.py', 'x/../file.py', 'x\nfile.py'])
def test_noncanonical_and_control_character_paths_rejected(tmp_path: Path, relative: str):
    with pytest.raises(ValueError, match='unsafe'):
        safe_path(tmp_path,relative,require_file=False)
