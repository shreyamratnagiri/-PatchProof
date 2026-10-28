"""Pure sandbox contracts; real Docker behavior is tested separately."""
from pathlib import Path
import packages.verification as verifier
import pytest


def test_framework_auto_unittest(tmp_path: Path):
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_math.py').write_text('import unittest\n')
    assert verifier._choose_python_framework(tmp_path, 'auto') == 'unittest'


def test_framework_auto_pytest(tmp_path: Path):
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'test_math.py').write_text('import pytest\ndef test_sum(): assert True\n')
    assert verifier._choose_python_framework(tmp_path, 'auto') == 'pytest'
    assert verifier._choose_python_framework(tmp_path, 'unittest') == 'unittest'
    with pytest.raises(ValueError):
        verifier._choose_python_framework(tmp_path, 'nosetests')


@pytest.mark.parametrize(('framework', 'stdout', 'stderr', 'number'), [
    ('unittest', '', 'Ran 0 tests in 0.000s\nOK', 0),
    ('unittest', '', 'Ran 3 tests in 0.004s\nOK', 3),
    ('pytest', 'no tests ran in 0.04s', '', 0),
    ('pytest', '2 passed, 1 skipped in 0.04s', '', 2),
    ('node', 'TAP version 13\n# tests 2\n# pass 2', '', 2),
])
def test_discovery_cannot_be_assumed(framework, stdout, stderr, number):
    assert verifier._test_count(framework, {'stdout': stdout, 'stderr': stderr}) == number


@pytest.mark.parametrize(('source','expected'), [
    ('import unittest\nclass T(unittest.TestCase):\n def test_true(self): self.assertTrue(True)\n','unittest'),
    ('import pytest\n\ndef test_ok(): assert 1 == 1\n','pytest'),
])
def test_container_framework_selection(tmp_path: Path, monkeypatch, source, expected):
    tests = tmp_path / 'tests'
    tests.mkdir()
    (tests / 'test_calc.py').write_text(source)
    monkeypatch.setattr(verifier.shutil, 'which', lambda _: '/usr/bin/docker')
    seen = []
    def run_fake(args, **kwargs):
        seen.append(args)
        return {'status': 'finished', 'exit_code': 0, 'stdout': '','stderr': 'Ran 0 tests in 0.00s\nOK'}
    monkeypatch.setattr(verifier, '_bounded_command', run_fake)
    monkeypatch.setattr(verifier.subprocess, 'run', lambda *_args, **_kwargs: None)
    result = verifier.verify(tmp_path)
    assert result['status'] == 'unavailable'  # exit=0 does not imply any tests ran
    assert result['verification'] == 'unproven'
    assert result['tests_run'] == 0
    assert result['framework'] == expected
    command = seen[0]
    assert command[command.index('--network') + 1] == 'none'
    assert command[command.index('--read-only') + 1] == '--cap-drop'
    assert verifier.PYTEST_IMAGE in command if expected == 'pytest' else verifier.PYTHON_IMAGE in command


def test_missing_dependency_is_not_success(tmp_path, monkeypatch):
    tests=tmp_path/'tests'; tests.mkdir()
    (tests/'test_missing.py').write_text('import package_that_is_not_installed\n')
    monkeypatch.setattr(verifier.shutil, 'which', lambda _: '/usr/bin/docker')
    def missing(*_a,**_kw):
        return {'status':'finished','exit_code':1,'stderr':'ImportError: No module named missing','stdout':''}
    monkeypatch.setattr(verifier,'_bounded_command',missing)
    monkeypatch.setattr(verifier.subprocess,'run',lambda *_a,**_kw:None)
    result=verifier.verify(tmp_path)
    assert result['status']=='failed' and result['verification']=='unproven'


def test_copy_budget_rejects_large_source(tmp_path, monkeypatch):
    tests=tmp_path/'tests'; tests.mkdir()
    (tests/'test_overbudget.py').write_text('import unittest')
    (tmp_path/'huge.dat').write_bytes(b'A'*2048)
    monkeypatch.setattr(verifier,'MAX_SANDBOX_BYTES',1024)
    monkeypatch.setattr(verifier.shutil,'which',lambda _: '/usr/bin/docker')
    result=verifier.verify(tmp_path)
    assert result['status']=='unavailable'
    assert 'budget' in result['reason']


def test_disposable_mount_root_is_accessible_to_container_uid(tmp_path, monkeypatch):
    import stat
    tests=tmp_path/'tests';tests.mkdir()
    (tests/'test_ok.py').write_text('import unittest\n')
    tmp_path.chmod(0o700)  # imported archive directory is intentionally private
    monkeypatch.setattr(verifier.shutil,'which',lambda _: '/usr/bin/docker')
    modes=[]
    def inspect_staged(command,**kwargs):
        mount=command[command.index('--mount')+1]
        source=next(part[4:] for part in mount.split(',') if part.startswith('src='))
        modes.append(stat.S_IMODE(Path(source).stat().st_mode))
        return {'status':'finished','exit_code':125,'stdout':'','stderr':''}
    monkeypatch.setattr(verifier,'_bounded_command',inspect_staged)
    monkeypatch.setattr(verifier.subprocess,'run',lambda *_a,**_kw:None)
    assert verifier.verify(tmp_path)['status']=='unavailable'
    assert modes==[0o755]
    assert stat.S_IMODE(tmp_path.stat().st_mode)==0o700


def test_plain_pytest_functions_are_detected_without_pytest_import(tmp_path: Path):
    tests = tmp_path / 'tests'
    tests.mkdir()
    (tests / 'test_arithmetic.py').write_text('def test_arithmetic():\n    assert 1 + 1 == 2\n')
    assert verifier._choose_python_framework(tmp_path, 'auto') == 'pytest'
    (tests / 'test_arithmetic.py').write_text('async def test_async_example():\n    assert True\n')
    assert verifier._choose_python_framework(tmp_path, 'auto') == 'pytest'


def test_sandbox_records_collection_and_dependency_failures(tmp_path: Path, monkeypatch):
    tests = tmp_path / 'tests'
    tests.mkdir()
    (tests / 'test_math.py').write_text('def test_math(): assert True\n')
    monkeypatch.setattr(verifier.shutil, 'which', lambda _: '/usr/bin/docker')
    monkeypatch.setattr(verifier.subprocess, 'run', lambda *_a, **_k: None)
    monkeypatch.setattr(verifier, '_bounded_command', lambda *_a, **_k: {
        'status': 'finished', 'exit_code': 2, 'stdout': '',
        'stderr': 'ERROR collecting tests/test_math.py\nModuleNotFoundError: No module named foo'})
    report = verifier.verify(tmp_path)
    assert report['status'] == 'failed'
    assert report['tests_run'] == 0
    assert report['verification'] == 'unproven'
    assert report['failure_category'] == 'missing_dependency_or_import_error'


def test_pytest_collection_error_explained_without_false_pass(tmp_path: Path, monkeypatch):
    tests = tmp_path / 'tests'
    tests.mkdir()
    (tests / 'test_math.py').write_text('def test_math(): assert True\n')
    monkeypatch.setattr(verifier.shutil, 'which', lambda _: '/usr/bin/docker')
    monkeypatch.setattr(verifier.subprocess, 'run', lambda *_a, **_k: None)
    monkeypatch.setattr(verifier, '_bounded_command', lambda *_a, **_k: {
        'status': 'finished', 'exit_code': 2, 'stdout': '',
        'stderr': 'ERROR collecting tests/test_math.py\nSyntaxError: invalid syntax'})
    report = verifier.verify(tmp_path)
    assert report['status'] == 'failed'
    assert report['failure_category'] == 'collection_error'


def test_sandbox_directory_budget_includes_empty_directories(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(verifier, 'MAX_SANDBOX_DIRECTORIES', 3)
    (tmp_path / 'tests').mkdir()
    for name in ('empty_one', 'empty_two', 'empty_three'):
        (tmp_path / name).mkdir()
    assert 'directory budget' in (verifier._validate_source_budget(tmp_path) or '')
