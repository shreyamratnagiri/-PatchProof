"""Contract-level tests. Never execute uploaded source on host."""
import io
import json
import stat
import zipfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
import packages.database as database
import apps.api.main as api

KEY={'X-PatchProof-Key':'test-key'}

def archive(**files):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
        for name,content in files.items():z.writestr(name,content)
    return out.getvalue()

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('PATCHPROOF_API_KEY','test-key')
    monkeypatch.setattr(api,'ROOT',tmp_path/'repos')
    api.ROOT.mkdir()
    engine=create_engine(f'sqlite:///{tmp_path}/test.sqlite')
    monkeypatch.setattr(database,'engine',engine)
    database.Session.configure(bind=engine)
    with TestClient(api.app) as c:
        yield c
    database.Session.configure(bind=database.engine)
    engine.dispose()

def test_auth_closed(client):
    assert client.get('/api/repositories').status_code==401
    assert client.get('/api/repositories',headers=KEY).status_code==200

def test_workflow_import_localize_review_export(client):
    zipped=archive(**{'calculator.py':'def add(a, b):\n    return a - b\n','tests/test_calculator.py':'import unittest\n'})
    response=client.post('/api/repositories/import',headers=KEY,files={'file':('calc.zip',zipped,'application/zip')})
    assert response.status_code==201,response.text
    repo=response.json()['id']
    duplicate=client.post('/api/repositories/import',headers=KEY,files={'file':('calc.zip',zipped,'application/zip')})
    assert duplicate.json()['id']==repo and duplicate.json()['duplicate'] is True
    assert len(client.get(f'/api/repositories/{repo}/graph',headers=KEY).json()['nodes'])==2
    issue=client.post('/api/issues',headers=KEY,json={'repository_id':repo,'description':'add function must return sum, currently gives difference'}).json()['id']
    investigation=client.post('/api/repairs',headers=KEY,json={'issue_id':issue,'method':'lexical','generate':False})
    assert investigation.status_code==201,investigation.text
    run=investigation.json()['id']
    assert investigation.json()['locations'][0]['path']=='calculator.py'
    patch=client.post(f'/api/repairs/{run}/candidates',headers=KEY,json={'path':'calculator.py','old':'return a - b','new':'return a + b','rationale':'The expected operation is addition.'})
    assert patch.status_code==201,patch.text
    assert '+    return a + b' in patch.json()['diff']
    assert (api.ROOT/repo/'calculator.py').read_text().endswith('return a - b\n')
    report=client.get(f'/api/repairs/{run}/report',headers=KEY)
    assert report.status_code==200
    assert report.json()['candidates'][0]['result']['verification']=='unproven'
    assert 'attachment' in report.headers['content-disposition']
    assert client.get(f'/api/repairs/{run}',headers=KEY).json()['status']=='generated'
    queued=client.post(f'/api/repairs/{run}/verify?candidate_id={patch.json()["id"]}',headers=KEY)
    assert queued.status_code==202,queued.text
    assert client.get(f'/api/jobs/{queued.json()["job_id"]}',headers=KEY).json()['status']=='queued'

def test_archive_validation(client):
    for filename in ('../escape.py','/root/abs.py','a\\..\\b.py','x/.git/config'):
        r=client.post('/api/repositories/import',headers=KEY,files={'file':('evil.zip',archive(**{filename:'payload'}),'application/zip')})
        assert r.status_code==400,(filename,r.text)
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as z:
        info=zipfile.ZipInfo('link.py')
        info.create_system=3
        info.external_attr=(stat.S_IFLNK|0o777)<<16
        z.writestr(info,'../../secret')
    r=client.post('/api/repositories/import',headers=KEY,files={'file':('link.zip',buf.getvalue(),'application/zip')})
    assert r.status_code==400,r.text

def test_invalid_scope_and_syntax(client):
    repo=client.post('/api/repositories/import',headers=KEY,files={'file':('single.zip',archive(**{'calc.py':'x=1\n'}),'application/zip')}).json()['id']
    issue=client.post('/api/issues',headers=KEY,json={'repository_id':repo,'description':'x should have value two'}).json()['id']
    run=client.post('/api/repairs',headers=KEY,json={'issue_id':issue}).json()['id']
    for path,new in [('../escape.py','x=2'),('other.py','x=2'),('calc.py','x=')]:
        result=client.post(f'/api/repairs/{run}/candidates',headers=KEY,json={'path':path,'old':'x=1','new':new,'rationale':'Replace incorrect assignment'})
        assert result.status_code==422,result.text

def test_database_restart_persistence(client):
    repo=client.post('/api/repositories/import',headers=KEY,files={'file':('persistent.zip',archive(**{'main.py':'pass\n'}),'application/zip')}).json()['id']
    from sqlalchemy.orm import sessionmaker
    session_again=sessionmaker(bind=database.Session.kw['bind'])
    with session_again() as session:
        assert session.get(database.Repository,repo).id==repo

def test_model_job_queue_and_persistence(client,monkeypatch):
    import time
    from packages.repair import LLMReplacement
    def model(issue,entries,**kwargs):
        assert 'operation' in issue
        return [LLMReplacement(path='calculator.py',old='a-b',new='a+b',rationale='Fix subtraction instead of addition')],'test-provider'
    monkeypatch.setattr(api,'ollama_candidates',model)
    zipped=archive(**{'calculator.py':'def add(a,b):\n    return a-b\n'})
    repo=client.post('/api/repositories/import',headers=KEY,files={'file':('calc.zip',zipped,'application/zip')}).json()['id']
    issue=client.post('/api/issues',headers=KEY,json={'repository_id':repo,'description':'Addition operation subtracts instead of adding'}).json()['id']
    run=client.post('/api/repairs',headers=KEY,json={'issue_id':issue}).json()['id']
    response=client.post(f'/api/repairs/{run}/generate',headers=KEY)
    assert response.status_code==202,response.text
    for _ in range(100):
        current=client.get(f'/api/jobs/{run}',headers=KEY).json()
        if current['status']=='generated':break
        time.sleep(.02)
    assert current['status']=='generated',current
    items=client.get(f'/api/repairs/{run}/candidates',headers=KEY).json()['items']
    assert len(items)==1 and items[0]['model']=='test-provider'
    assert (api.ROOT/repo/'calculator.py').read_text().endswith('return a-b\n')


def test_docker_unavailability_explicit(client,monkeypatch):
    import packages.verification as sandbox
    monkeypatch.setattr(sandbox.shutil,'which',lambda _:None)
    with __import__('tempfile').TemporaryDirectory() as td:
        assert sandbox.verify(__import__('pathlib').Path(td))['status']=='unavailable'


def test_run_creation_returns_same_core_schema_as_retrieval(client_from_api):
    client, _api, key = client_from_api
    # Use a separate known-valid fixture without changing candidate data.
    import io
    import zipfile
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('calculator.py', 'def add(a,b):\n return a-b\n')
    repository = client.post('/api/repositories/import', files={'file': ('r.zip', stream.getvalue(), 'application/zip')}, headers=key).json()
    issue = client.post('/api/issues', json={'repository_id': repository['id'], 'description': 'Addition returns subtraction instead of addition'}, headers=key).json()
    response = client.post('/api/repairs', json={'issue_id': issue['id'], 'method': 'lexical'}, headers=key)
    assert response.status_code == 201
    run = response.json()
    saved = client.get(f"/api/repairs/{run['id']}", headers=key).json()
    assert run == saved
    assert run['repository_id'] == repository['id']
    assert run['issue_id'] == issue['id']
