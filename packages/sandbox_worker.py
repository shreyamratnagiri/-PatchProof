"""TRUSTED HOST-SIDE worker; never imported by the public API.

Runs as a separate OS process on an operator-controlled machine with Docker CLI,
a private repository directory, and database access. Single-tenant only.
Usage: python -m packages.sandbox_worker [--once]
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import os
import shutil
import signal
import tempfile
import time
import uuid
from pathlib import Path
from threading import Event, Thread
from sqlalchemy import select

from packages.database import Session, Candidate, RepairRun, VerificationJob, AuditEvent
from packages.ingest import safe_path
from packages.verification import verify, _docker_env, _validate_source_budget
from packages.verification_jobs import claim, finish, renew

LOG = logging.getLogger('patchproof.sandbox_worker')
STOP = Event()


def _repo_root(repo_id: str) -> Path:
    return Path(os.environ.get('PATCHPROOF_DATA', tempfile.gettempdir() + '/patchproof-data')).resolve() / str(uuid.UUID(repo_id))


def _sanitized_copy(source: Path, dest: Path) -> None:
    # Preserve symbolic links during copying to prevent traversal of links into
    # private host files; then delete links in the disposable tree only.
    problem = _validate_source_budget(source)
    if problem:
        raise ValueError(problem)
    shutil.copytree(source, dest, symlinks=True,
                    ignore=shutil.ignore_patterns('.git', '.env', '.venv', 'node_modules', '__pycache__'))
    for p in dest.rglob('*'):
        if p.is_symlink():
            p.unlink()
        elif p.is_file():
            p.chmod(0o600)


def _evaluate(job_id: str) -> dict:
    with Session() as db:
        job = db.get(VerificationJob, job_id)
        if job is None:
            raise ValueError('job not found')
        candidate = db.get(Candidate, job.candidate_id)
        run = db.get(RepairRun, job.run_id)
        if candidate is None or run is None or candidate.run_id != run.id or job.candidate_id != candidate.id:
            raise ValueError('job ownership mismatch')
        source_root = _repo_root(run.repository_id)
        target_path = candidate.path
        expected = candidate.original
        changed = candidate.updated
        regression = candidate.regression_test
        candidate_id = candidate.id

    def cancelled() -> bool:
        if STOP.is_set():
            return True
        with Session() as db:
            state = db.scalar(select(VerificationJob.status).where(VerificationJob.id == job_id))
            return state != 'running'

    if not source_root.is_dir():
        raise ValueError('repository artifact is missing')
    with tempfile.TemporaryDirectory(prefix='patchproof-worker-') as directory:
        scratch = Path(directory)
        original_tree, patched_tree = scratch / 'original', scratch / 'patched'
        _sanitized_copy(source_root, original_tree)
        _sanitized_copy(original_tree, patched_tree)
        path = safe_path(patched_tree, target_path)
        if not path.is_file() or path.read_text('utf-8') != expected:
            raise ValueError('repository artifact differs from original candidate')
        path.write_text(changed, encoding='utf-8')
        # Only claim test evidence for languages with a supported isolated runner.
        runtime = ('python' if Path(target_path).suffix == '.py' else
                   'node' if Path(target_path).suffix == '.js' else None)
        existing = (verify(patched_tree, cancelled=cancelled, timeout=30, runtime=runtime, job_id=job_id)
                    if runtime is not None else
                    {'status': 'unsupported', 'verification': 'unproven',
                     'reason': 'JSX/TypeScript patches require an explicitly configured test runner; Python tests are not evidence.'})
        regression_result: dict = {'status': 'not_generated'}
        if regression and runtime == 'python' and not cancelled():
            name = 'test_patchproof_regression_' + candidate_id.replace('-', '') + '.py'
            before_path = original_tree / 'tests' / name
            after_path = patched_tree / 'tests' / name
            for target in (before_path, after_path):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(regression, encoding='utf-8')
            before = verify(original_tree, cancelled=cancelled, pattern=name, timeout=30, job_id=job_id)
            after = verify(patched_tree, cancelled=cancelled, pattern=name, timeout=30, job_id=job_id) if not cancelled() else {
                'status': 'cancelled', 'verification':'unproven'}
            regression_result = {
                'status': 'passed' if before['status'] == 'failed' and after['status'] == 'passed' else 'unverified',
                'baseline': before, 'patched': after,
                'criterion': 'Fail on original, pass on modified copy (isolated allowlisted Python runner).',
            }
        if regression and runtime != 'python':
            regression_result = {'status':'unsupported', 'reason':'Generated Python regression tests only supported for Python targets'}
    if cancelled():
        return {'verification':'unproven','status':'cancelled','existing_tests':existing,
                'regression_tests':regression_result}
    verified = ('existing_and_regression_tests_passed_only' if existing['status']=='passed' and regression_result['status']=='passed'
                else 'existing_tests_passed_only' if existing['status']=='passed' else 'unproven')
    return {'syntax':'passed','verification':verified, 'existing_tests':existing,
            'regression_tests':regression_result, 'formal_properties':'not_checked'}


def work_once(worker_id: str) -> bool:
    with Session.begin() as db:
        job = claim(db, worker_id)
        if job is None:
            return False
        identifier = job.id
    # Heartbeat while Docker may be pulling/starting or while successive
    # original/patched regression tests run. Without this, queue polling can
    # mark an active container as interrupted after the claim lease expires.
    heartbeat_stop = Event()
    def heartbeat() -> None:
        while not heartbeat_stop.wait(20):
            try:
                with Session.begin() as db:
                    if not renew(db, identifier, worker_id):
                        heartbeat_stop.set()
                        return
            except Exception:
                LOG.exception('Could not renew lease for verification job %s', identifier)
                # Fail closed: subsequent cancellation checks see a failed lease.
                heartbeat_stop.set()
                return
    heartbeat_thread = Thread(target=heartbeat, name='patchproof-job-heartbeat', daemon=True)
    heartbeat_thread.start()
    try:
        result = _evaluate(identifier)
        status = ('cancelled' if result.get('status')=='cancelled' else
                  'timed_out' if result['existing_tests']['status']=='timeout' else
                  'completed' if result['existing_tests']['status']=='passed' else 'failed')
    except Exception as exc:
        LOG.exception('Verification job %s failed', identifier)
        result = {'verification': 'unproven', 'reason':type(exc).__name__ + ': ' + str(exc)[:400]}
        status = 'failed'
    finally:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=3)
    with Session.begin() as db:
        if finish(db,identifier,worker_id,result,status):
            job = db.get(VerificationJob, identifier)
            candidate = db.get(Candidate,job.candidate_id)
            if candidate is not None:
                candidate.result = result
                evidence_status = result.get('existing_tests', {}).get('status')
                candidate.status = (
                    'tests_passed' if result.get('verification', 'unproven') != 'unproven'
                    else 'verification_unsupported' if evidence_status == 'unsupported'
                    else 'verification_unavailable' if evidence_status == 'unavailable'
                    else 'verification_timed_out' if evidence_status == 'timeout'
                    else 'verification_cancelled' if evidence_status == 'cancelled'
                    else 'tests_failed'
                )
            db.add(AuditEvent(action='verification.finished',object_id=identifier,detail={'status':status}))
    return True


def cleanup_orphans() -> int:
    """At single-worker startup, remove only PatchProof-owned leftover containers.

    This does not stop another service's containers. Multi-worker deployments
    are intentionally unsupported; a second worker must not run this sweep.
    """
    if not shutil.which('docker'):
        LOG.warning('Docker CLI unavailable: abandoned sandbox cleanup cannot run')
        return 0
    try:
        listing = subprocess.run(['docker','ps','-aq','--filter','label=patchproof.owner=trusted-worker'],
                                 capture_output=True, text=True, timeout=10, env=_docker_env(), check=False)
        if listing.returncode:
            LOG.warning('Could not query orphaned sandbox containers')
            return 0
        ids = [line for line in listing.stdout.splitlines() if len(line) in range(12, 65) and
               all(char in '0123456789abcdef' for char in line)]
        if not ids:
            return 0
        removed = subprocess.run(['docker','rm','-f',*ids[:128]], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, timeout=25, env=_docker_env(), check=False)
        if removed.returncode:
            LOG.warning('Orphan cleanup did not complete successfully')
        return len(ids[:128]) if removed.returncode == 0 else 0
    except (subprocess.TimeoutExpired, OSError):
        LOG.warning('Orphan cleanup unavailable; inspect Docker containers manually')
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description='Trusted Docker orchestration worker; no web listener')
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--poll-seconds', type=float, default=1.0)
    args = parser.parse_args()
    if not .2 <= args.poll_seconds <= 60:
        parser.error('poll interval must be 0.2..60 seconds')
    logging.basicConfig(level=logging.INFO)
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    cleanup_orphans()
    worker = str(uuid.uuid4())
    while not STOP.is_set():
        found = work_once(worker)
        if args.once:
            break
        if not found:
            STOP.wait(args.poll_seconds)

if __name__ == '__main__':
    main()
