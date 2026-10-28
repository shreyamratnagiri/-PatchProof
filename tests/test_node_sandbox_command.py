"""The JavaScript runner is Docker-only; this test checks its command contract."""
from pathlib import Path
from packages import verification


def test_node_runner_uses_disposable_no_network_container(tmp_path: Path, monkeypatch):
    tests = tmp_path / 'tests'
    tests.mkdir()
    (tests / 'math.test.js').write_text("import test from 'node:test'; test('one',()=>{});\n")
    calls = []
    monkeypatch.setattr(verification.shutil, 'which', lambda name: '/usr/bin/docker')
    monkeypatch.setattr(verification, '_bounded_command', lambda command, **_: (
        calls.append(command) or {'status': 'finished', 'exit_code': 0, 'stdout': '# tests 1\n# pass 1', 'stderr': ''}))
    monkeypatch.setattr(verification.subprocess, 'run', lambda *args, **kwargs: None)
    result = verification.verify(tmp_path, runtime='node')
    command = calls[0]
    assert result['status'] == 'passed'
    assert '--network' in command and command[command.index('--network') + 1] == 'none'
    assert 'node:22-alpine' in command
    assert command[-3:] == ['node', '--test', 'tests/math.test.js']
    assert '--read-only' in command and '--cap-drop' in command
    assert all('python' not in token for token in command[-3:])


def test_node_runner_requires_actual_supported_tests(tmp_path: Path):
    (tmp_path / 'tests').mkdir()
    (tmp_path / 'tests' / 'readme.md').write_text('not a test')
    result = verification.verify(tmp_path, runtime='node')
    assert result['status'] == 'unavailable'
    assert result['verification'] == 'unproven'
