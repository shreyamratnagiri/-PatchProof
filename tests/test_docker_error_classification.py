"""Docker command failures must not be mislabeled as failed repository tests."""
from pathlib import Path
import pytest
from packages import verification


@pytest.mark.parametrize('exit_code', [125, 126, 127])
def test_docker_start_failure_fails_closed(tmp_path: Path, monkeypatch, exit_code: int):
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_one.py').write_text('import unittest\n')
    monkeypatch.setattr(verification.shutil, 'which', lambda name: '/usr/bin/docker')
    monkeypatch.setattr(verification, '_bounded_command', lambda *args, **kwargs: {
        'status': 'finished', 'exit_code': exit_code, 'stdout': '', 'stderr': 'failed to start'
    })
    # The Docker cleanup attempt is harmless and independent of the mocked
    # return code. No repository code runs on the host.
    monkeypatch.setattr(verification.subprocess, 'run', lambda *args, **kwargs: None)
    report = verification.verify(tmp_path)
    assert report['status'] == 'unavailable'
    assert report['verification'] == 'unproven'
