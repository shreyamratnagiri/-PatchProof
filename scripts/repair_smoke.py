"""Real API workflow, optional actual Ollama generation and Docker verification.

Does not run repository code on the host. Only the trusted synthetic fixture is
submitted as data; the Docker-only verifier executes its unittest suite.
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import zipfile
import subprocess
import shutil
from fastapi.testclient import TestClient
from apps.api.main import app


def require(response):
    if response.status_code >= 400:
        raise RuntimeError(f'{response.status_code}: {response.text[:500]}')
    return response.json()


def main() -> int:
    key = os.environ.get('PATCHPROOF_API_KEY')
    if not key:
        print('BLOCKED: PATCHPROOF_API_KEY is not configured', file=sys.stderr)
        return 2
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as file:
        file.writestr('calculator.py', 'def add(a,b):\n    return a - b\n')
        file.writestr('tests/test_calculator.py', '''import unittest\nfrom calculator import add\nclass TestCalculator(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(1,2),3)\n''')
    try:
        if not shutil.which('docker') or not shutil.which('ollama'):
            raise RuntimeError('Docker CLI and Ollama CLI required for model + isolated repair smoke')
        # Host-side worker is a separate trusted process, not the API process.
        worker=subprocess.Popen([sys.executable,'-m','packages.sandbox_worker','--poll-seconds','0.5'],
                                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
          with TestClient(app) as client:
            auth = {'X-PatchProof-Key': key}
            repo = require(client.post('/api/repositories/import', headers=auth,
                files={'file': ('trusted-repair-fixture.zip', archive.getvalue(), 'application/zip')}))
            issue = require(client.post('/api/issues', headers=auth, json={'repository_id': repo['id'],
                'description': 'The calculator addition function returns a subtraction result.',
                'expected': 'add(1,2) must return 3', 'observed': 'add(1,2) returns -1'}))
            repair = require(client.post('/api/repairs', headers=auth, json={
                'issue_id': issue['id'], 'method': 'lexical', 'generate': False}))
            if not repair['locations']:
                raise RuntimeError('No localized code candidates')
            queued = require(client.post(f"/api/repairs/{repair['id']}/generate", headers=auth))
            print('Generation job:', queued['status'])
            status = None
            for _ in range(150):
                status = require(client.get(f"/api/jobs/{repair['id']}", headers=auth))
                if status['status'] not in {'queued', 'running'}:
                    break
                time.sleep(1)
            if status['status'] != 'generated':
                raise RuntimeError('AI patch generation incomplete: ' + json.dumps(status))
            patches = require(client.get(f"/api/repairs/{repair['id']}/candidates", headers=auth))['items']
            if not patches:
                raise RuntimeError('No generated patch candidate')
            for patch in patches:
                validation = require(client.post(f"/api/repairs/{repair['id']}/verify",
                    headers=auth, params={'candidate_id': patch['id']}))
                job_id=validation['job_id']
                for _ in range(100):
                    outcome=require(client.get('/api/jobs/'+job_id,headers=auth))
                    if outcome['status'] not in {'queued','running'}:break
                    time.sleep(1)
                if outcome['status']!='completed':
                    raise RuntimeError('candidate verification failed or unavailable: '+json.dumps(outcome))
                print(json.dumps({'candidate':patch['id'],'status':outcome['status'],
                    'verification':outcome['result'].get('verification','unproven')}))
            report = require(client.get(f"/api/repairs/{repair['id']}/report", headers=auth))
            print(json.dumps({'run': repair['id'], 'candidates': len(report['candidates']),
                              'model': patches[0]['model']}))
            if not any(c['result'].get('existing_tests', {}).get('status') == 'passed'
                       for c in report['candidates']):
                raise RuntimeError('No generated patch passed existing Docker-isolated tests')
            return 0
        finally:
          worker.terminate()
          try: worker.wait(timeout=5)
          except subprocess.TimeoutExpired: worker.kill();worker.wait(timeout=5)
    except Exception as exc:
        print('REPAIR SMOKE FAILED:', type(exc).__name__, str(exc)[:500], file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
