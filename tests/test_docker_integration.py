"""Docker tests use the real daemon (no Docker client mocking). They are
skipped, not reported as passing, if the trusted test host lacks Docker.
"""
from __future__ import annotations
import shutil
import subprocess
from pathlib import Path
import pytest
from packages.verification import verify


def _daemon_available() -> bool:
    if not shutil.which('docker'):
        return False
    try:
        return subprocess.run(['docker','info','--format','{{.ServerVersion}}'],
                              capture_output=True,timeout=8).returncode == 0
    except (OSError,subprocess.TimeoutExpired):
        return False

pytestmark=pytest.mark.skipif(not _daemon_available(),reason='Docker CLI/daemon unavailable')

@pytest.mark.parametrize(('program','expected','timeout'),[
    ('import unittest\nclass T(unittest.TestCase):\n def test_yes(self): self.assertTrue(True)\n','passed',15),
    ('import unittest\nclass T(unittest.TestCase):\n def test_no(self): self.assertTrue(False)\n','failed',15),
    ('import unittest,time\nclass T(unittest.TestCase):\n def test_loop(self):\n  while True: time.sleep(.1)\n','timeout',2),
    ('import unittest,socket\nclass T(unittest.TestCase):\n def test_net(self):\n  with self.assertRaises(OSError):socket.create_connection(("1.1.1.1",80),timeout=1)\n','passed',15),
])
def test_actual_restricted_container(tmp_path:Path,program:str,expected:str,timeout:int):
    folder=tmp_path/'tests';folder.mkdir()
    (folder/'test_fixture.py').write_text(program)
    report=verify(tmp_path,timeout=timeout)
    assert report['status']==expected,report
    status=subprocess.run(['docker','ps','-a','--filter','name=patchproof-',
                           '--format','{{.Names}}'],capture_output=True,text=True,timeout=8)
    assert status.returncode==0
    assert not status.stdout.strip(),status.stdout


def test_actual_node_builtin_test_runner(tmp_path: Path):
    folder = tmp_path / 'tests'
    folder.mkdir()
    (folder / 'calculator.test.js').write_text("const test = require('node:test');\nconst assert = require('node:assert/strict');\ntest('addition', () => assert.equal(1+2,3));\n")
    result = verify(tmp_path, runtime='node', timeout=20)
    assert result['status'] == 'passed', result


def test_actual_pytest_success_and_failure(tmp_path: Path):
    folder = tmp_path / 'tests'
    folder.mkdir()
    (folder / 'test_example.py').write_text('import pytest\ndef test_value(): assert 2 + 2 == 4\n')
    good = verify(tmp_path, timeout=30)
    assert good['status'] == 'passed' and good['framework'] == 'pytest' and good['tests_run'] == 1, good
    (folder / 'test_example.py').write_text('import pytest\ndef test_value(): assert 2 + 2 == 5\n')
    bad = verify(tmp_path, timeout=30)
    assert bad['status'] == 'failed' and bad['verification'] == 'unproven', bad


def test_actual_zero_unittest_tests_is_unverified(tmp_path: Path):
    folder = tmp_path / 'tests'
    folder.mkdir()
    (folder / 'test_empty.py').write_text('import unittest\nclass Nothing(unittest.TestCase): pass\n')
    result = verify(tmp_path, timeout=15)
    assert result['status'] == 'unavailable' and result['verification'] == 'unproven', result


def test_actual_pytest_collection_error_is_failure(tmp_path: Path):
    folder = tmp_path / 'tests'
    folder.mkdir()
    (folder / 'test_collection.py').write_text('import pytest\nimport missing_nonexistent_dependency_987654\n')
    result = verify(tmp_path, timeout=25)
    assert result['status'] == 'failed' and result['verification'] == 'unproven', result
