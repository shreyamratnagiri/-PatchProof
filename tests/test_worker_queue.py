"""Validate real database CAS queue transitions; worker execution is Docker-only."""
from __future__ import annotations
import io
import zipfile
from datetime import timedelta
from packages.database import Session, VerificationJob, Candidate, now
from packages.verification_jobs import claim, finish
import packages.sandbox_worker as worker


def setup_job(client, key):
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w') as zip_file:
        zip_file.writestr('logic.py','def add(a,b):\n    return a-b\n')
        zip_file.writestr('tests/test_logic.py','import unittest\n')
    repo=client.post('/api/repositories/import',headers=key,files={'file':('r.zip',data.getvalue(),'application/zip')}).json()['id']
    issue=client.post('/api/issues',headers=key,json={'repository_id':repo,'description':'The add function should add, not subtract its operands'}).json()['id']
    run=client.post('/api/repairs',headers=key,json={'issue_id':issue}).json()['id']
    candidate=client.post(f'/api/repairs/{run}/candidates',headers=key,json={'path':'logic.py','old':'return a-b','new':'return a+b','rationale':'Fix arithmetic error'}).json()['id']
    return run,candidate


def test_queue_single_claim_and_cancel(client_from_api):
    client,api,key=client_from_api
    run,candidate=setup_job(client,key)
    url=f'/api/repairs/{run}/verify?candidate_id={candidate}'
    assert client.post(url,headers=key).status_code==202
    assert client.post(url,headers=key).status_code==409
    with Session.begin() as db:
        claimed=claim(db,'worker-a')
        assert claimed is not None and claimed.status=='running'
        job_id=claimed.id
    with Session.begin() as db:
        assert claim(db,'worker-b') is None
    assert client.post(f'/api/jobs/{job_id}/cancel',headers=key).status_code==200
    with Session.begin() as db:
        assert finish(db,job_id,'worker-a',{'verification':'existing_tests_passed_only'},'completed') is False
    assert client.get(f'/api/jobs/{job_id}',headers=key).json()['status']=='cancelled'
    assert client.post(url,headers=key).status_code==202


def test_worker_persists_result_and_never_resurrects_cancelled(client_from_api,monkeypatch):
    client,api,key=client_from_api
    run,candidate=setup_job(client,key)
    submit=client.post(f'/api/repairs/{run}/verify?candidate_id={candidate}',headers=key).json()
    monkeypatch.setattr(worker,'_evaluate',lambda job_id:{'verification':'existing_tests_passed_only','existing_tests':{'status':'passed'},'regression_tests':{'status':'not_generated'}})
    assert worker.work_once('worker-1') is True
    job=client.get(f'/api/jobs/{submit["job_id"]}',headers=key).json()
    assert job['status']=='completed'
    assert job['result']['verification']=='existing_tests_passed_only'
    with Session() as db:
        assert db.get(Candidate,candidate).status=='tests_passed'
    assert worker.work_once('worker-1') is False


def test_recover_expired_job_with_explicit_retry(client_from_api):
    client,api,key=client_from_api
    run,candidate=setup_job(client,key)
    submit=client.post(f'/api/repairs/{run}/verify?candidate_id={candidate}',headers=key).json()
    with Session.begin() as db:
        current=claim(db,'dead-worker',seconds=1)
        assert current.id==submit['job_id']
        current.lease_until=now()-timedelta(seconds=1)
    with Session.begin() as db:
        assert claim(db,'new-worker') is None
    status=client.get(f'/api/jobs/{submit["job_id"]}',headers=key).json()
    assert status['status']=='interrupted'
    assert client.post(f'/api/repairs/{run}/verify?candidate_id={candidate}',headers=key).status_code==202


def test_worker_does_not_execute_untrusted_code_on_host(client_from_api,monkeypatch):
    client,api,key=client_from_api
    run,candidate=setup_job(client,key)
    queued=client.post(f'/api/repairs/{run}/verify?candidate_id={candidate}',headers=key).json()
    monkeypatch.setattr(worker,'verify',lambda root,**kwargs:{'status':'unavailable','verification':'unproven','reason':'No Docker'})
    monkeypatch.setenv('PATCHPROOF_DATA',str(api.ROOT))
    assert worker.work_once('sandbox-host-test')
    status=client.get(f'/api/jobs/{queued["job_id"]}',headers=key).json()
    assert status['status']=='failed'
    assert status['result']['existing_tests']['status']=='unavailable'


def test_worker_lease_renewal_requires_owner_and_active_job(client_from_api):
    from packages.verification_jobs import renew
    client, api, key = client_from_api
    run, candidate = setup_job(client, key)
    response = client.post(f'/api/repairs/{run}/verify?candidate_id={candidate}', headers=key)
    job_id = response.json()['job_id']
    with Session.begin() as db:
        claimed = claim(db, 'actual-owner', seconds=60)
        assert claimed.id == job_id
        original = claimed.lease_until
    with Session.begin() as db:
        assert not renew(db, job_id, 'different-worker')
        assert renew(db, job_id, 'actual-owner', seconds=180)
    with Session() as db:
        assert db.get(VerificationJob, job_id).lease_until > original
    assert client.post(f'/api/jobs/{job_id}/cancel', headers=key).status_code == 200
    with Session.begin() as db:
        assert not renew(db, job_id, 'actual-owner')


def test_unsupported_language_job_does_not_claim_failed_tests(client_from_api, monkeypatch):
    client, api, key = client_from_api
    run, candidate = setup_job(client, key)
    submission = client.post(f'/api/repairs/{run}/verify?candidate_id={candidate}', headers=key)
    job_id = submission.json()['job_id']
    monkeypatch.setattr(worker, '_evaluate', lambda _: {
        'verification': 'unproven',
        'existing_tests': {'status': 'unsupported', 'verification': 'unproven'},
        'regression_tests': {'status': 'not_generated'},
    })
    assert worker.work_once('trusted-worker-unsupported') is True
    with Session() as db:
        item = db.get(Candidate, candidate)
        assert item.status == 'verification_unsupported'
    item_response = client.get(f'/api/jobs/{job_id}', headers=key)
    assert item_response.json()['result']['existing_tests']['status'] == 'unsupported'
