"""Run against a dedicated ephemeral PostgreSQL test DB, not application data.

Invoke with PATCHPROOF_TEST_DATABASE_URL pointing to a separate disposable DB.
Never repurpose the production database URL for this test.
"""
from __future__ import annotations
import os
import uuid
import pytest
from sqlalchemy import create_engine, select, text
from packages.database import Repository, Issue, RepairRun, Candidate, AuditEvent, VerificationJob, Base


def test_postgres_transaction_and_job_record():
    url=os.environ.get('PATCHPROOF_TEST_DATABASE_URL')
    if not url:
        if os.getenv('PATCHPROOF_REQUIRE_POSTGRES') == '1':
            pytest.fail('PostgreSQL integration is required but test database is missing')
        pytest.skip('Dedicated PostgreSQL test database not configured')
    if not url.startswith('postgresql+psycopg://') or not url.split('?',1)[0].rsplit('/',1)[-1].endswith('_test'):
        pytest.fail('Refusing to run outside a dedicated *_test PostgreSQL database')
    engine=create_engine(url,pool_pre_ping=True)
    from sqlalchemy.orm import Session
    repo_id=str(uuid.uuid4()); issue_id=str(uuid.uuid4()); run_id=str(uuid.uuid4()); candidate_id=str(uuid.uuid4()); job_id=str(uuid.uuid4())
    try:
        with engine.begin() as conn:
            rows=conn.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public'")).scalars().all()
        assert {'repositories','issues','repair_runs','candidates','verification_jobs'}.issubset(set(rows)), 'Apply Alembic migrations first'
        with Session(engine) as db:
            db.add(Repository(id=repo_id,name='pg test',digest=uuid.uuid4().hex,status='indexed',file_count=0,indexed=[]))
            db.flush()
            db.add(Issue(id=issue_id,repository_id=repo_id,description='A dedicated integration test'))
            db.flush()
            db.add(RepairRun(id=run_id,repository_id=repo_id,issue_id=issue_id,status='localized',method='lexical',locations=[]))
            db.flush()
            db.add(Candidate(id=candidate_id,run_id=run_id,path='test.py',original='x=1',updated='x=2',diff='',rationale='testing',result={}))
            db.flush()
            db.add(VerificationJob(id=job_id,run_id=run_id,candidate_id=candidate_id,status='queued',result={}))
            db.commit()
        # Persistence across distinct DB sessions and transaction boundaries.
        with Session(engine) as db:
            assert db.get(VerificationJob,job_id).status=='queued'
            db.get(VerificationJob,job_id).status='cancelled'
            db.commit()
        with Session(engine) as db:
            assert db.get(VerificationJob,job_id).status=='cancelled'
    finally:
        # Cleanup only records created by this test, never drop tables or data.
        with Session(engine) as db:
            db.query(VerificationJob).filter_by(id=job_id).delete()
            db.query(Candidate).filter_by(id=candidate_id).delete()
            db.query(RepairRun).filter_by(id=run_id).delete()
            db.query(Issue).filter_by(id=issue_id).delete()
            db.query(Repository).filter_by(id=repo_id).delete()
            db.commit()
        engine.dispose()
