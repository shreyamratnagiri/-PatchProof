"""Docker-only disposable execution for allowlisted Python/Node test frameworks.

No host execution fallback. The Docker daemon is trusted infrastructure; ordinary
Docker isolation is not a safe boundary for hostile multi-tenant submissions.
"""
from __future__ import annotations

import os
import re
import stat
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

PYTHON_IMAGE = 'python:3.12-alpine'
# Built by the trusted operator from docker/pytest-runner.Dockerfile. Never install
# dependencies in an untrusted repository or enable networking in test containers.
PYTEST_IMAGE = 'patchproof-pytest:3.12-9.0.2'
NODE_IMAGE = 'node:22-alpine'
IMAGE = PYTHON_IMAGE  # Backward-compatible default for sandbox option tests.
OUTPUT_LIMIT = 12_000
MAX_SANDBOX_FILES = 2500
MAX_SANDBOX_DIRECTORIES = 4000
MAX_SANDBOX_BYTES = 32 * 1024 * 1024
# Trusted runner logic executes only *inside* the resource-limited container.
# unittest discovery normally exits 0 for zero collected tests: prohibit that.
UNITTEST_RUNNER = (
    'import sys,unittest; '
    'suite=unittest.defaultTestLoader.discover("tests",pattern=sys.argv[1]); '
    'count=suite.countTestCases(); '
    'result=unittest.TextTestRunner(verbosity=1).run(suite) if count else None; '
    'sys.exit(0 if result is not None and result.wasSuccessful() else 5)'
)


def _docker_env() -> dict[str, str]:
    """Docker CLI environment only. None of these variables enter the worker."""
    keys = ('PATH', 'SYSTEMROOT', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'HOME', 'DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_CONFIG')
    return {key: os.environ[key] for key in keys if key in os.environ}


def _bounded_command(command: list[str], *, timeout: int, cancelled: Callable[[], bool] | None) -> dict:
    """Drain stdout/stderr without unbounded RAM use, and kill on timeout/cancel."""
    started = time.monotonic()
    outputs = [bytearray(), bytearray()]
    try:
        child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_docker_env())
    except OSError as exc:
        return {'status': 'unavailable', 'reason': str(exc)[:250], 'verification': 'unproven'}

    def drain(stream, target: bytearray):
        try:
            while chunk := stream.read(8192):
                remaining = OUTPUT_LIMIT - len(target)
                if remaining > 0:
                    target.extend(chunk[:remaining])
        finally:
            stream.close()

    workers = [threading.Thread(target=drain, args=(stream, output), daemon=True)
               for stream, output in zip((child.stdout, child.stderr), outputs)]
    for worker in workers:
        worker.start()
    outcome = 'finished'
    while child.poll() is None:
        if cancelled and cancelled():
            outcome = 'cancelled'
            child.kill()
            break
        if time.monotonic() - started >= timeout:
            outcome = 'timeout'
            child.kill()
            break
        time.sleep(.05)
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=5)
    for worker in workers:
        worker.join(timeout=2)
    return {
        'status': outcome,
        'exit_code': child.returncode,
        'duration_ms': round((time.monotonic() - started) * 1000),
        'stdout': outputs[0].decode('utf-8', 'replace'),
        'stderr': outputs[1].decode('utf-8', 'replace'),
        'output_truncated': any(len(output) == OUTPUT_LIMIT for output in outputs),
    }


def _choose_python_framework(root: Path, framework: str) -> str:
    """Only unittest and pytest are supported; unknown frameworks are not guessed.

    Explicit choice takes precedence. Auto-selection uses recognized test metadata
    and bounded scans, never imports or executes repository code on the host.
    """
    if framework not in {'auto', 'unittest', 'pytest'}:
        raise ValueError('unsupported Python test framework')
    if framework != 'auto':
        return framework
    if (root / 'pytest.ini').is_file() or (root / 'tests' / 'conftest.py').is_file():
        return 'pytest'
    pyproject = root / 'pyproject.toml'
    if pyproject.is_file() and pyproject.stat().st_size <= 64_000:
        if '[tool.pytest' in pyproject.read_text('utf-8', errors='replace'):
            return 'pytest'
    for path in sorted((root / 'tests').rglob('test*.py'))[:MAX_SANDBOX_FILES]:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 128_000:
            continue
        source = path.read_text('utf-8', errors='replace')
        if re.search(r'(?m)^(?:import pytest\b|from pytest import\b|@pytest\.|(?:async )?def test_[A-Za-z0-9_]*\s*\()', source):
            return 'pytest'
    return 'unittest'


def _test_count(framework: str, result: dict) -> int:
    """Require executable evidence that at least one test ran to claim success."""
    output = result.get('stdout', '') + '\n' + result.get('stderr', '')
    if framework == 'unittest':
        matches = re.findall(r'(?m)^Ran (\d+) tests? in ', output)
        return int(matches[-1]) if matches else 0
    if framework == 'pytest':
        # pytest -q prints summaries including e.g. '3 passed, 1 skipped in'.
        matches = re.findall(r'\b(\d+) passed\b', output)
        return int(matches[-1]) if matches else 0
    if framework == 'node':
        matches = re.findall(r'(?m)^# tests (\d+)\s*$', output)
        return int(matches[-1]) if matches else 0
    return 0


def _validate_source_budget(root: Path) -> str | None:
    """Bound copies before staging. Symlinks are not dereferenced."""
    count = 0
    directory_count = 0
    bytes_total = 0
    for parent, dirs, files in os.walk(root, followlinks=False):
        directory_count += 1
        if directory_count > MAX_SANDBOX_DIRECTORIES:
            return 'sandbox directory budget exceeded' 
        dirs[:] = [d for d in dirs if d not in {'.git','.venv','node_modules','__pycache__'}
                  and not (Path(parent) / d).is_symlink()]
        for name in files:
            file = Path(parent) / name
            if file.is_symlink():
                continue
            count += 1
            if count > MAX_SANDBOX_FILES:
                return 'sandbox file budget exceeded'
            try:
                metadata = file.lstat()
            except OSError:
                return 'sandbox source metadata unavailable'
            if not stat.S_ISREG(metadata.st_mode):
                return 'sandbox contains an unsupported special file'
            bytes_total += metadata.st_size
            if bytes_total > MAX_SANDBOX_BYTES:
                return 'sandbox size budget exceeded'
    return None


def verify(root: Path, *, timeout: int = 30, cancelled: Callable[[], bool] | None = None,
           pattern: str = 'test*.py', runtime: str = 'python', job_id: str | None = None,
           framework: str = 'auto') -> dict:
    if job_id is not None:
        try:
            job_id = str(uuid.UUID(job_id))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError('invalid verification job identifier') from exc
    if runtime not in {'python', 'node'}:
        raise ValueError('unsupported sandbox runtime')
    if runtime == 'node' and framework not in {'auto', 'node'}:
        raise ValueError('Python test framework cannot run in Node.js sandbox')
    if runtime == 'python' and framework not in {'auto', 'unittest', 'pytest'}:
        raise ValueError('unsupported Python test framework')
    if runtime == 'python' and not re.fullmatch(r'test(?:\*|_patchproof_regression_[0-9a-f]{32})\.py', pattern):
        raise ValueError('unsupported test discovery pattern')
    if runtime == 'node' and pattern != 'test*.py':
        raise ValueError('Python regression discovery is not supported with Node.js')
    if not 1 <= timeout <= 120:
        raise ValueError('timeout must be 1..120 seconds')
    if cancelled and cancelled():
        return {'status': 'cancelled', 'verification': 'unproven', 'reason': 'Cancelled before sandbox startup'}
    if not shutil.which('docker'):
        return {'status': 'unavailable', 'reason': 'Docker CLI not installed; untrusted tests were not executed', 'verification': 'unproven'}
    if not (root / 'tests').is_dir():
        return {'status': 'unavailable', 'reason': 'No tests/ directory; no test execution attempted', 'verification': 'unproven'}
    budget_error = _validate_source_budget(root)
    if budget_error:
        return {'status':'unavailable','verification':'unproven','reason':budget_error}
    chosen = _choose_python_framework(root, framework) if runtime == 'python' else 'node'
    node_tests: list[str] = []
    if runtime == 'node':
        for p in sorted((root / 'tests').rglob('*.js')):
            if p.is_symlink() or not p.is_file():
                continue
            if p.name.startswith('test_') or p.name.endswith('.test.js'):
                node_tests.append(p.relative_to(root).as_posix())
                if len(node_tests) > 50:
                    return {'status':'unavailable', 'reason':'Node.js test-file limit exceeded', 'verification':'unproven'}
        if not node_tests:
            return {'status':'unavailable', 'reason':'No supported Node.js test files in tests/', 'verification':'unproven'}

    # This temporary directory is controlled by the trusted orchestrator.
    with tempfile.TemporaryDirectory(prefix='patchproof-sandbox-') as scratch:
        staged = Path(scratch) / 'source'
        # symlinks=True ensures the copy NEVER dereferences links into host files.
        shutil.copytree(root, staged, symlinks=True,
                        ignore=shutil.ignore_patterns('.git', '.env', '.venv', 'node_modules', '__pycache__'))
        # copytree preserves the root's restrictive mode (often 0700). The
        # container's unprivileged UID must be able to traverse the root of
        # this disposable read-only mount. Never chmod the original import.
        staged.chmod(0o755)
        for path in staged.rglob('*'):
            if path.is_symlink():
                path.unlink()
            elif path.is_dir():
                path.chmod(0o755)
            elif path.is_file():
                # Imported files are intentionally 0600; the unprivileged
                # container UID needs read access only to this disposable copy.
                path.chmod(0o644)
        container_name = 'patchproof-' + uuid.uuid4().hex
        command = [
            'docker', 'run', '--name', container_name, '--rm',
            '--label', 'patchproof.owner=trusted-worker',
            *(['--label', 'patchproof.job=' + job_id] if job_id else []),
            '--network', 'none',
            '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--pids-limit', '64', '--memory', '256m', '--cpus', '1',
            '--user', '65534:65534', '--tmpfs', '/tmp:rw,noexec,nosuid,size=32m',
            '--env', 'PYTHONDONTWRITEBYTECODE=1',
            '--env', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD=1',
            '--mount', f'type=bind,src={staged},dst=/workspace,readonly',
            '--workdir', '/workspace',
            (PYTEST_IMAGE if chosen == 'pytest' else PYTHON_IMAGE if chosen == 'unittest' else NODE_IMAGE),
            *(['python', '-c', UNITTEST_RUNNER, pattern]
              if chosen == 'unittest' else
              ['python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-o', 'addopts=',
               'tests/' + pattern] if chosen == 'pytest' and pattern != 'test*.py' else
              ['python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-o', 'addopts=', 'tests']
              if chosen == 'pytest' else ['node', '--test', *node_tests]),
        ]
        try:
            result = _bounded_command(command, timeout=timeout, cancelled=cancelled)
        finally:
            # --rm is best-effort only; force-cleanup is required on timeouts,
            # cancellation, and Docker client errors.
            try:
                subprocess.run(['docker', 'rm', '-f', container_name],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=10, check=False, env=_docker_env())
            except (OSError, subprocess.TimeoutExpired):
                pass
        if result['status'] in {'cancelled', 'timeout', 'unavailable'}:
            return {**result, 'verification': 'unproven',
                    'reason': result.get('reason', f"Sandbox {result['status']}; cleanup requested")}
        # Docker CLI exit codes 125/126/127 indicate daemon, image or command startup failures.
        if result['exit_code'] in (125, 126, 127):
            return {**result, 'status': 'unavailable', 'verification': 'unproven',
                    'reason': 'Docker CLI/daemon could not start sandbox'}
        tests_run = _test_count(chosen, result)
        passed = result['exit_code'] == 0 and tests_run > 0
        if result['exit_code'] == 0 and tests_run == 0:
            return {**result, 'status': 'unavailable', 'verification': 'unproven',
                    'framework': chosen, 'tests_run': 0,
                    'reason': 'Test runner did not demonstrate that any tests executed'}
        failure_category = None
        if not passed:
            output = result.get('stdout', '') + '\n' + result.get('stderr', '')
            if re.search(r'(?:ModuleNotFoundError|ImportError|Cannot find module|No module named)', output):
                failure_category = 'missing_dependency_or_import_error'
            elif re.search(r'(?:ERROR collecting|Interrupted: .* errors? during collection)', output):
                failure_category = 'collection_error'
            else:
                failure_category = 'test_failure_or_runner_error'
        return {**result, 'status': 'passed' if passed else 'failed',
                **({'failure_category': failure_category} if failure_category else {}),
                'framework': chosen, 'tests_run': tests_run,
                'verification': 'existing_tests_passed' if passed else 'unproven',
                'note': chosen + ' ran in isolated Docker; passing tests are not formal proof.'}
