"""Persistent single-tenant verification queue and worker claims.

The API can enqueue jobs but MUST NOT have access to a Docker daemon. A separate
trusted host-side worker (started by an operator) claims jobs and runs Docker.
The worker and API share the database and a private repository directory.
"""
from __future__ import annotations

from datetime import timedelta, timezone
from uuid import uuid4
from sqlalchemy import func, select, update, text
from sqlalchemy.orm import Session as DBSession
from packages.database import Candidate, RepairRun, VerificationJob, now

ACTIVE = ('queued', 'running')
MAX_QUEUED = 32


def enqueue(db: DBSession, run_id: str, candidate_id: str) -> VerificationJob:
    # Serialized by locking the candidate on PostgreSQL. SQLite transactions are
    # only supported for a single API instance (see SECURITY.md).
    # Lock a single, transaction-scoped admission mutex across API instances.
    # A candidate row lock alone protects duplicate submissions for that candidate,
    # not the global MAX_QUEUED budget when distinct candidates race.
    if db.bind is not None and db.bind.dialect.name == 'postgresql':
        db.execute(text('SELECT pg_advisory_xact_lock(705194208)'))
    candidate = db.scalar(select(Candidate).where(Candidate.id == candidate_id).with_for_update())
    if candidate is None or candidate.run_id != run_id:
        raise ValueError('candidate is not part of this repair run')
    run = db.get(RepairRun, run_id)
    if run is None or run.repository_id is None:
        raise ValueError('repair run unavailable')
    active = db.scalar(select(VerificationJob.id).where(VerificationJob.candidate_id == candidate_id,
                                                      VerificationJob.status.in_(ACTIVE)).limit(1))
    if active:
        raise RuntimeError('candidate already has an active verification')
    count = db.scalar(select(func.count(VerificationJob.id)).where(VerificationJob.status == 'queued')) or 0
    if count >= MAX_QUEUED:
        raise OverflowError('verification queue capacity reached')
    job = VerificationJob(id=str(uuid4()), run_id=run_id, candidate_id=candidate_id,
                          status='queued', result={}, created_at=now())
    db.add(job)
    db.flush()
    return job


def claim(db: DBSession, worker_id: str, *, seconds: int = 180) -> VerificationJob | None:
    """Atomic compare-and-swap claim; expired running jobs are marked interrupted.

    A crashed job is NOT retried automatically: retry must be explicit because
    duplicate container execution may cause unexpected resource consumption.
    """
    expired = now()
    db.execute(update(VerificationJob).where(VerificationJob.status == 'running',
                                             VerificationJob.lease_until < expired)
               .values(status='interrupted', completed_at=expired,
                       result={'verification':'unproven','reason':'worker lease expired'}))
    job_id = db.scalar(select(VerificationJob.id).where(VerificationJob.status == 'queued')
                             .order_by(VerificationJob.created_at, VerificationJob.id).limit(1))
    if job_id is None:
        return None
    until = expired + timedelta(seconds=seconds)
    changed = db.execute(update(VerificationJob).where(VerificationJob.id == job_id,
                  VerificationJob.status == 'queued').values(status='running', worker_id=worker_id,
                  lease_until=until, started_at=expired))
    if changed.rowcount != 1:
        return None
    db.flush()
    return db.get(VerificationJob, job_id)


def renew(db: DBSession, job_id: str, worker_id: str, *, seconds: int = 180) -> bool:
    """Extend only an active lease owned by this worker (not a cancelled job)."""
    if seconds < 30 or seconds > 600:
        raise ValueError('invalid verification lease duration')
    changed = db.execute(update(VerificationJob).where(
        VerificationJob.id == job_id, VerificationJob.worker_id == worker_id,
        VerificationJob.status == 'running'
    ).values(lease_until=now() + timedelta(seconds=seconds)))
    return changed.rowcount == 1


def finish(db: DBSession, job_id: str, worker_id: str, result: dict, status: str) -> bool:
    if status not in {'completed', 'failed', 'timed_out', 'cancelled', 'interrupted'}:
        raise ValueError('invalid terminal job state')
    changed = db.execute(update(VerificationJob).where(VerificationJob.id == job_id,
                    VerificationJob.worker_id == worker_id, VerificationJob.status == 'running')
                    .values(status=status, result=result, completed_at=now(), lease_until=None))
    return changed.rowcount == 1


def cancel(db: DBSession, job_id: str) -> bool:
    changed = db.execute(update(VerificationJob).where(VerificationJob.id == job_id,
                            VerificationJob.status.in_(ACTIVE))
                         .values(status='cancelled',completed_at=now(),lease_until=None))
    return changed.rowcount == 1


def info(job: VerificationJob) -> dict:
    return {'id':job.id,'run_id':job.run_id,'candidate_id':job.candidate_id,
            'status':job.status,'worker_id':job.worker_id,'created_at':(job.created_at if job.created_at.tzinfo else job.created_at.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat(),
            'result':job.result}
