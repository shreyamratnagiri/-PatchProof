"""PostgreSQL-only integration: separate connections compete for one durable job.

Runs only with PATCHPROOF_TEST_DATABASE_URL ending in '_test'. The CI postgres
job provides it and creates the schema through Alembic. No production fallback.
"""
from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from packages.database import Candidate, Issue, RepairRun, Repository, VerificationJob
from packages.verification_jobs import claim, finish


def _test_engine():
    url = os.getenv('PATCHPROOF_TEST_DATABASE_URL', '')
    if not url:
        if os.getenv('PATCHPROOF_REQUIRE_POSTGRES') == '1':
            pytest.fail('PostgreSQL integration is required but test database is missing')
        pytest.skip('A dedicated PostgreSQL test database is required')
    database_name = url.split('?', 1)[0].rsplit('/', 1)[-1]
    if not url.startswith('postgresql+psycopg://') or not database_name.endswith('_test'):
        pytest.fail('Refusing to write into a non-test PostgreSQL database')
    return create_engine(url, pool_pre_ping=True)


def test_postgres_single_atomic_claim_and_rollback():
    engine = _test_engine()
    repo_id, issue_id, run_id, candidate_id, job_id = [str(uuid.uuid4()) for _ in range(5)]
    try:
        with Session(engine) as db:
            db.add(Repository(id=repo_id, name='postgres-claim-fixture', digest=uuid.uuid4().hex,
                              status='indexed', file_count=0, indexed=[]))
            db.flush()
            db.add(Issue(id=issue_id, repository_id=repo_id, description='Concurrent claim fixture'))
            db.flush()
            db.add(RepairRun(id=run_id, repository_id=repo_id, issue_id=issue_id, status='localized',
                             method='lexical', locations=[]))
            db.flush()
            db.add(Candidate(id=candidate_id, run_id=run_id, path='module.py', original='x=1',
                             updated='x=2', diff='', rationale='postgres fixture', result={}))
            db.flush()
            db.add(VerificationJob(id=job_id, run_id=run_id, candidate_id=candidate_id,
                                   status='queued', result={}))
            db.commit()

        def race(worker_id: str) -> str | None:
            with Session(engine) as db:
                job = claim(db, worker_id)
                claimed_id = job.id if job else None
                db.commit()
                return claimed_id

        with ThreadPoolExecutor(max_workers=4) as pool:
            claimed = list(pool.map(race, ['one', 'two', 'three', 'four']))
        assert claimed.count(job_id) == 1, claimed
        assert claimed.count(None) == 3, claimed
        with Session(engine) as db:
            job = db.get(VerificationJob, job_id)
            assert job.status == 'running'
            winning_worker = job.worker_id
        with Session(engine) as db:
            assert not finish(db, job_id, 'wrong-worker', {'verification': 'unproven'}, 'completed')
            assert finish(db, job_id, winning_worker, {'verification': 'existing_tests_passed_only'}, 'completed')
            db.commit()
        with Session(engine) as db:
            assert db.get(VerificationJob, job_id).status == 'completed'
            assert db.get(VerificationJob, job_id).result['verification'] == 'existing_tests_passed_only'

        # A deliberate rollback must not corrupt or remove the committed records.
        with pytest.raises(RuntimeError, match='rollback fixture'):
            with Session(engine) as db:
                db.get(VerificationJob, job_id).status = 'failed'
                db.flush()
                raise RuntimeError('rollback fixture')
        with Session(engine) as db:
            assert db.get(VerificationJob, job_id).status == 'completed'
    finally:
        with Session(engine) as db:
            db.query(VerificationJob).filter_by(id=job_id).delete()
            db.query(Candidate).filter_by(id=candidate_id).delete()
            db.query(RepairRun).filter_by(id=run_id).delete()
            db.query(Issue).filter_by(id=issue_id).delete()
            db.query(Repository).filter_by(id=repo_id).delete()
            db.commit()
        engine.dispose()
