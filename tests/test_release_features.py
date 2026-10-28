"""Release regression tests: real HTTP contracts, state transitions, and bounded host orchestration.

Only trusted test fixture code is executed on the host. Untrusted repository
contents are never run outside the Docker verifier.
"""
from __future__ import annotations

import io
import sys
import time
import threading
import zipfile
from pathlib import Path

from packages.intelligence import index_repository, dependency_graph
from packages.verification import _bounded_command, OUTPUT_LIMIT


def _zip(**sources: str) -> bytes:
    memory = io.BytesIO()
    with zipfile.ZipFile(memory, 'w') as bundle:
        for path, source in sources.items():
            bundle.writestr(path, source)
    return memory.getvalue()


def test_patch_approval_export_requires_consent(client_from_api):
    client, api, key = client_from_api
    repo = client.post('/api/repositories/import', headers=key,
                       files={'file': ('a.zip', _zip(**{'app.py': 'def add(a,b):\n    return a-b\n'}), 'application/zip')}).json()['id']
    issue = client.post('/api/issues', headers=key, json={'repository_id': repo,
              'description': 'An addition operation accidentally subtracts its second operand.'}).json()['id']
    run = client.post('/api/repairs', headers=key, json={'issue_id': issue}).json()['id']
    response = client.post(f'/api/repairs/{run}/candidates', headers=key,
        json={'path': 'app.py', 'old': 'return a-b', 'new': 'return a+b',
              'rationale': 'The return statement subtracts instead of adding.'})
    assert response.status_code == 201, response.text
    candidate = response.json()['id']
    url = f'/api/repairs/{run}/candidates/{candidate}/patch'
    assert client.get(url, headers=key).status_code == 409
    approved = client.post(f'/api/repairs/{run}/candidates/{candidate}/approve', headers=key)
    assert approved.status_code == 200
    assert approved.json()['verified'] == 'unproven'
    assert client.get(url, headers=key).status_code == 200
    assert '+    return a+b' in client.get(url, headers=key).text
    listed = client.get(f'/api/repairs/{run}/candidates', headers=key).json()['items']
    assert listed[0]['approved_at'] is not None
    assert (api.ROOT / repo / 'app.py').read_text().endswith('return a-b\n')
    # Approval must not authorize exporting a different run's candidates.
    other = client.post('/api/repairs', headers=key, json={'issue_id': issue}).json()['id']
    assert client.get(f'/api/repairs/{other}/candidates/{candidate}/patch', headers=key).status_code == 404


def test_cancel_running_model_does_not_resurrect(client_from_api, monkeypatch):
    client, api, key = client_from_api
    from packages.repair import LLMReplacement
    entered = threading.Event()
    release = threading.Event()

    def blocked_model(issue, entries, **kwargs):
        entered.set()
        assert release.wait(5)
        return [LLMReplacement(path='service.py', old='return x-1', new='return x+1',
                   rationale='Expected increment instead of decrement')], 'blocking-test-provider'

    monkeypatch.setattr(api, 'ollama_candidates', blocked_model)
    repo = client.post('/api/repositories/import', headers=key, files={'file': ('s.zip',
        _zip(**{'service.py': 'def increment(x):\n    return x-1\n'}), 'application/zip')}).json()['id']
    issue = client.post('/api/issues', headers=key, json={'repository_id': repo,
        'description': 'The increment helper returns x minus one and should add one.'}).json()['id']
    run = client.post('/api/repairs', headers=key, json={'issue_id': issue}).json()['id']
    try:
        assert client.post(f'/api/repairs/{run}/generate', headers=key).status_code == 202
        assert entered.wait(5)
        assert client.post(f'/api/repairs/{run}/generate', headers=key).status_code == 409
        assert client.post(f'/api/jobs/{run}/cancel', headers=key).json()['status'] == 'cancelled'
    finally:
        release.set()
    for _ in range(100):
        status = client.get(f'/api/jobs/{run}', headers=key).json()['status']
        if status == 'cancelled':
            break
        time.sleep(.01)
    # The model may complete after cancellation, but cannot write candidates.
    for _ in range(100):
        with api.JOBS_LOCK:
            pending = run in api.JOBS
        if not pending:
            break
        time.sleep(.01)
    assert client.get(f'/api/jobs/{run}', headers=key).json()['status'] == 'cancelled'
    assert client.get(f'/api/repairs/{run}/candidates', headers=key).json()['items'] == []


def test_bounded_command_output_and_timeout():
    # This command is a trusted internal fixture, NOT repository code.
    emitted = _bounded_command([sys.executable, '-c', 'import sys;sys.stdout.write("z"*50000)'],
                               timeout=20, cancelled=None)
    assert emitted['status'] == 'finished'
    assert emitted['exit_code'] == 0
    assert len(emitted['stdout']) <= OUTPUT_LIMIT
    assert emitted['output_truncated']
    timed = _bounded_command([sys.executable, '-c', 'import time;time.sleep(5)'],
                             timeout=1, cancelled=None)
    assert timed['status'] == 'timeout'


def test_relative_import_dependency_graph(tmp_path: Path):
    pkg = tmp_path / 'pkg'
    pkg.mkdir()
    (pkg / 'helper.py').write_text('def hello():\n    return 1\n')
    (pkg / 'main.py').write_text('from .helper import hello\n')
    entries = index_repository(tmp_path)
    assert {'source': 'pkg/main.py', 'target': 'pkg/helper.py'} in dependency_graph(entries)['edges']


def test_archive_rejects_file_parent_collision(client_from_api):
    client, _, key = client_from_api
    blob = _zip(**{'module.py': 'x=1\n', 'module.py/child.py': 'x=2\n'})
    response = client.post('/api/repositories/import', headers=key,
        files={'file': ('collision.zip', blob, 'application/zip')})
    assert response.status_code == 400
    assert 'conflicts' in response.json()['detail']


def test_candidate_duplicate_is_rejected(client_from_api):
    client, _, key = client_from_api
    repo = client.post('/api/repositories/import', headers=key, files={'file':(
        'duplicate.zip', _zip(**{'module.py':'def add(a,b):\n    return a-b\n'}),'application/zip')}).json()['id']
    issue = client.post('/api/issues',headers=key,json={'repository_id':repo,
        'description':'Addition must return the sum of two input numbers.'}).json()['id']
    run = client.post('/api/repairs',headers=key,json={'issue_id':issue}).json()['id']
    candidate = {'path':'module.py','old':'return a-b','new':'return a+b',
                 'rationale':'Use addition rather than subtraction.'}
    first=client.post(f'/api/repairs/{run}/candidates',headers=key,json=candidate)
    assert first.status_code == 201, first.text
    duplicate=client.post(f'/api/repairs/{run}/candidates',headers=key,json=candidate)
    assert duplicate.status_code == 422
    assert 'duplicate' in duplicate.json()['detail']
    assert len(client.get(f'/api/repairs/{run}/candidates',headers=key).json()['items']) == 1
