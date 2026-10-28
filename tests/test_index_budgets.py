"""Regression checks for bounded repository traversal and indexing."""
from pathlib import Path
import pytest

from packages import intelligence


def test_unsupported_and_oversized_source_does_not_enter_index(tmp_path: Path):
    (tmp_path / 'ok.py').write_text('def healthy():\n    return 1\n')
    (tmp_path / 'large.py').write_bytes(b'x' * 750_001)
    (tmp_path / 'notes.txt').write_text('ignored')
    (tmp_path / 'node_modules').mkdir()
    (tmp_path / 'node_modules' / 'ignore.py').write_text('not source')
    assert [item['path'] for item in intelligence.index_repository(tmp_path)] == ['ok.py']


def test_index_is_bounded_even_for_many_uninteresting_files(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(intelligence, 'MAX_SCANNED', 3)
    for i in range(15):
        (tmp_path / f'{i:02d}.txt').write_text('not source')
    (tmp_path / 'good.py').write_text('def foo(): return 2')
    assert intelligence.index_repository(tmp_path) == []


def test_index_excludes_symlinks(tmp_path: Path):
    import os
    (tmp_path / 'ok.py').write_text('def ok(): return True')
    try:
        (tmp_path / 'link.py').symlink_to(tmp_path / 'ok.py')
        (tmp_path / 'alias_dir').symlink_to(tmp_path, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip('host prohibits symlink creation; sandbox path test requires supported OS')
    assert [item['path'] for item in intelligence.index_repository(tmp_path)] == ['ok.py']
