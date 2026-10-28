from pathlib import Path
from packages.verification import verify

def test_reject_invalid_deadline(tmp_path: Path):
    try: verify(tmp_path, timeout=0)
    except ValueError: pass
    else: raise AssertionError('Expected deadline rejection')

def test_missing_tests_or_docker_returns_unproven(tmp_path: Path):
    result=verify(tmp_path)
    assert result['verification']=='unproven'
    assert result['status']=='unavailable'
