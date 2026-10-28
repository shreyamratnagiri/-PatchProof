"""PatchProof API: authenticated import, persisted analysis, scoped repairs, sandbox verification.

Unsafe repositories are never imported as Python modules or executed on host.
"""
from __future__ import annotations
import hashlib
import json
import logging
import time
import os
import shutil
import tempfile
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from concurrent.futures import Future, ThreadPoolExecutor
from threading import BoundedSemaphore, Event, Lock
from pathlib import Path
from typing import Annotated
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from packages.database import Session, Repository, Issue, RepairRun, Candidate, AuditEvent, VerificationJob, init_db
from packages.ingest import MAX_ZIP, extract_archive, safe_path
from packages.git_import import clone_public_github, github_url
from packages.intelligence import index_repository, dependency_graph
from packages.retrieval import rank
from packages.repair import LLMReplacement, candidate_diff, ollama_candidates
from packages.properties import check_linear_int_property
from packages.candidate_ranking import candidate_priority
from packages.verification_jobs import enqueue, cancel as cancel_verification, info as verification_info

EXECUTOR = ThreadPoolExecutor(max_workers=2,thread_name_prefix='patchproof-repair')
QUEUE_SLOTS = BoundedSemaphore(4)
IMPORT_SLOTS = BoundedSemaphore(2)
JOBS: dict[str,tuple[Future, Event]] = {}
JOBS_LOCK = Lock()

ROOT = Path(os.environ.get('PATCHPROOF_DATA',tempfile.gettempdir()+'/patchproof-data')).resolve()
ROOT.mkdir(parents=True,exist_ok=True)

@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    from sqlalchemy import update
    with Session.begin() as db:
        db.execute(update(RepairRun).where(RepairRun.status.in_(['queued','running'])).values(status='interrupted',explanation='Application restarted during an in-memory job. Re-submit explicitly.'))
    yield

app=FastAPI(title='PatchProof API', version='0.3.0', lifespan=lifespan)
LOGGER = logging.getLogger('patchproof.api')
RATE_LOCK = Lock()
RATE_BUCKETS: dict[str, tuple[float,int]] = {}

@app.middleware('http')
async def protective_request_middleware(request: Request, call_next):
    # In-process protection, not a substitute for gateway rate limits.
    from fastapi.responses import JSONResponse as ErrorResponse
    start=time.monotonic()
    request_id=str(uuid.uuid4())
    ip=request.client.host if request.client else 'unknown'
    now=time.monotonic()
    with RATE_LOCK:
        if len(RATE_BUCKETS)>2000:
            RATE_BUCKETS.clear()
        window,count=RATE_BUCKETS.get(ip,(now,0))
        if now-window>=60:
            window,count=now,0
        RATE_BUCKETS[ip]=(window,count+1)
        throttled=count>=120
    content_length=request.headers.get('content-length')
    if throttled:
        response=ErrorResponse({'detail':'per-client request rate exceeded'},status_code=429)
    elif content_length and (not content_length.isdecimal() or int(content_length)>17_000_000):
        response=ErrorResponse({'detail':'request body exceeds configured budget'},status_code=413)
    else:
        response=await call_next(request)
    response.headers['X-Request-ID']=request_id
    LOGGER.info(json.dumps({'event':'request','id':request_id,'method':request.method,'path':request.url.path[:180],
                            'status':response.status_code,'duration_ms':round((time.monotonic()-start)*1000,2)}))
    return response

def auth(x_patchproof_key: Annotated[str | None, Header()] = None) -> None:
    expected = os.environ.get('PATCHPROOF_API_KEY')
    if not expected:
        raise HTTPException(503,'PATCHPROOF_API_KEY is required for protected actions')
    import hmac
    if not x_patchproof_key or not hmac.compare_digest(expected,x_patchproof_key):
        raise HTTPException(401,'invalid API key')

Protect = Depends(auth)

def get_id(identifier: str) -> str:
    try:return str(uuid.UUID(identifier))
    except ValueError as exc:raise HTTPException(422,'invalid identifier') from exc

def get_repo(db, identifier: str) -> Repository:
    repo = db.get(Repository,get_id(identifier))
    if repo is None:raise HTTPException(404,'repository not found')
    return repo

def repo_root(identifier: str) -> Path:
    return ROOT/get_id(identifier)

def get_run(db, identifier: str) -> RepairRun:
    run = db.get(RepairRun,get_id(identifier))
    if run is None:raise HTTPException(404,'repair run not found')
    return run

def audit(db, action: str, object_id: str, **detail) -> None:
    db.add(AuditEvent(action=action,object_id=object_id,detail=detail))

def utc_iso(value: datetime) -> str:
    """SQLAlchemy SQLite drops timezone metadata; timestamps are persisted in UTC."""
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()


def repo_info(repo: Repository) -> dict:
    return {'id':repo.id,'name':repo.name,'status':repo.status,'files':repo.file_count,'digest':repo.digest,'created_at':utc_iso(repo.created_at)}

def candidate_info(candidate: Candidate) -> dict:
    return {'id':candidate.id,'path':candidate.path,'diff':candidate.diff,
            'rationale':candidate.rationale,'model':candidate.model,'status':candidate.status,
            'approved_at':utc_iso(candidate.approved_at) if candidate.approved_at else None,
            'result':candidate.result,'priority':candidate_priority(candidate.diff,candidate.result)}

def run_info(run: RepairRun) -> dict:
    return {'id':run.id,'repository_id':run.repository_id,'issue_id':run.issue_id,'status':run.status,'method':run.method,'locations':run.locations,'explanation':run.explanation,'created_at':utc_iso(run.created_at)}

class GitImportRequest(BaseModel):
    url: str = Field(min_length=24,max_length=300)

@app.post('/api/repositories/git',dependencies=[Protect],status_code=201)
def import_public_git(request:GitImportRequest):
    try:normalized=github_url(request.url)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    digest=hashlib.sha256(('git:'+normalized).encode()).hexdigest()
    with Session() as db:
        exists=db.scalar(select(Repository).where(Repository.digest==digest))
        if exists:return {**repo_info(exists),'duplicate':True}
    rid=str(uuid.uuid4());folder=repo_root(rid)
    try:
        _,count=clone_public_github(normalized,folder)
        entries=index_repository(folder)
        with Session.begin() as db:
            item=Repository(id=rid,name=normalized.rsplit('/',1)[-1],digest=digest,file_count=len(entries),status='indexed',indexed=[{'path':r['path'],'symbols':r['symbols'],'imports':r['imports'],'valid':r['valid'],'language':r['language']} for r in entries])
            db.add(item);audit(db,'repository.git_imported',rid,url=normalized,file_count=count)
        return {**repo_info(item),'duplicate':False}
    except ValueError as exc:
        shutil.rmtree(folder,ignore_errors=True)
        raise HTTPException(422,str(exc)) from exc

class IssueRequest(BaseModel):
    repository_id: str
    description: str = Field(min_length=10,max_length=6000)
    expected: str = Field(default='',max_length=3000)
    observed: str = Field(default='',max_length=3000)

class RepairRequest(BaseModel):
    issue_id: str
    method: str = Field(default='lexical',pattern='^(lexical|semantic|hybrid)$')
    generate: bool = False

class ManualCandidate(BaseModel):
    path: str
    old: str = Field(min_length=1,max_length=8000)
    new: str = Field(max_length=8000)
    rationale: str = Field(min_length=5,max_length=2000)
    regression_test: str = Field(default='',max_length=10000)

class PropertyRequest(BaseModel):
    variables: list[str]
    assumptions: list[dict]
    conclusion: dict

@app.get('/health')
def health():return {'status':'ok','service':'PatchProof'}

@app.get('/ready')
def ready():
    try:
        with Session() as db:
            db.execute(select(Repository.id).limit(1)).all()
        return {'ready':True,'database':'reachable','docker': bool(shutil.which('docker')),'model':'external optional; see /api/status','verification':'separate trusted worker required'}
    except Exception:
        raise HTTPException(503,'database not ready') from None

@app.get('/api/model/health',dependencies=[Protect])
def model_health():
    """Probe configured Ollama locally; never report configuration as inference success."""
    import httpx
    url=os.environ.get('PATCHPROOF_OLLAMA_URL','http://127.0.0.1:11434').rstrip('/')
    try:
        with httpx.Client(timeout=3,trust_env=False) as client:
            response=client.get(url+'/api/tags')
            response.raise_for_status()
            tags=response.json().get('models',[])
        return {'available':True,'models':[str(model.get('name',''))[:120] for model in tags],
                'patch_model':os.environ.get('PATCHPROOF_PATCH_MODEL','qwen2.5-coder:7b'),
                'embed_model':os.environ.get('PATCHPROOF_EMBED_MODEL','nomic-embed-text'),
                'warning':'Model listing is not evidence of successful generation or embeddings.'}
    except (httpx.HTTPError,ValueError,KeyError) as exc:
        return {'available':False,'reason':type(exc).__name__,
                'warning':'Model generation and semantic retrieval require a running configured provider.'}

@app.get('/api/status',dependencies=[Protect])
def status():
    return {'api':'ready','sandbox_cli_available':bool(shutil.which('docker')),'trusted_worker_required':True,'api_executes_repository_tests':False,'database_backend':Session.kw['bind'].dialect.name,
            'ollama_configured':bool(os.environ.get('PATCHPROOF_OLLAMA_URL')),'authentication':'enabled',
            'limitations':['Model inference is external; ranking methods requiring embeddings fail closed if unavailable.',
                           'Test execution requires Docker; Docker CLI existence does not guarantee daemon availability.',
                           'No source-based formal verification; Z3 supports only supplied bounded integer constraints.']}

@app.post('/api/repositories/import',dependencies=[Protect],status_code=201)
async def import_repo(file: UploadFile = File(...)):
    data=await file.read(MAX_ZIP+1)
    if len(data)>MAX_ZIP:raise HTTPException(413,'ZIP too large')
    digest=hashlib.sha256(data).hexdigest()
    with Session() as db:
        existing=db.scalar(select(Repository).where(Repository.digest==digest))
        if existing:return {**repo_info(existing),'duplicate':True}
    if not IMPORT_SLOTS.acquire(blocking=False):
        raise HTTPException(429,'concurrent repository import limit reached')
    identifier=str(uuid.uuid4())
    folder=repo_root(identifier)
    try:
        # Archive decompression + AST indexing are CPU/IO heavy; never block
        # FastAPI's event loop with them.
        await run_in_threadpool(extract_archive,data,folder)
        entries=await run_in_threadpool(index_repository,folder)
        with Session.begin() as db:
            item=Repository(id=identifier,name=(file.filename or 'upload.zip')[:256],digest=digest,file_count=len(entries),status='indexed',indexed=[{'path':r['path'],'symbols':r['symbols'],'imports':r['imports'],'valid':r['valid'],'language':r['language']} for r in entries])
            db.add(item);audit(db,'repository.imported',identifier,file_count=len(entries))
        return {**repo_info(item),'duplicate':False}
    except Exception as exc:
        shutil.rmtree(folder,ignore_errors=True)
        if isinstance(exc,(ValueError,EOFError, __import__('zipfile').BadZipFile)):
            raise HTTPException(400,str(exc)) from exc
        if isinstance(exc,IntegrityError):raise HTTPException(409,'duplicate repository import') from exc
        raise
    finally:
        IMPORT_SLOTS.release()

@app.get('/api/repositories',dependencies=[Protect])
def repositories(limit:int=Query(default=30,ge=1,le=100),offset:int=Query(default=0,ge=0)):
    with Session() as db:
        return {'items':[repo_info(x) for x in db.scalars(select(Repository).order_by(Repository.created_at.desc()).offset(offset).limit(limit))], 'limit':limit,'offset':offset}

@app.get('/api/repositories/{identifier}',dependencies=[Protect])
def repository(identifier:str):
    with Session() as db:
        item=get_repo(db,identifier)
        return {**repo_info(item),'entries':item.indexed}

@app.get('/api/repositories/{identifier}/graph',dependencies=[Protect])
def graph(identifier:str):
    with Session() as db:get_repo(db,identifier)
    return dependency_graph(index_repository(repo_root(identifier)))

@app.get('/api/repositories/{identifier}/file',dependencies=[Protect])
def file_content(identifier: str,path:str=Query(min_length=1,max_length=500)):
    with Session() as db:get_repo(db,identifier)
    try:
        target=safe_path(repo_root(identifier),path)
        if target.suffix not in {'.py','.js','.ts','.jsx','.tsx'}:
            raise ValueError('unsupported text file')
        return {'path':path,'content':target.read_text('utf-8')}
    except (ValueError,UnicodeError) as exc: raise HTTPException(422,str(exc)) from exc

@app.post('/api/issues',dependencies=[Protect],status_code=201)
def create_issue(request:IssueRequest):
    identifier=str(uuid.uuid4())
    with Session.begin() as db:
        get_repo(db,request.repository_id)
        db.add(Issue(id=identifier,repository_id=request.repository_id,description=request.description,expected=request.expected,observed=request.observed))
        audit(db,'issue.created',identifier)
    return {'id':identifier,'repository_id':request.repository_id}

@app.get('/api/issues',dependencies=[Protect])
def list_issues(repository_id:str | None=None,limit:int=Query(default=40,ge=1,le=100)):
    with Session() as db:
        stmt=select(Issue).order_by(Issue.created_at.desc()).limit(limit)
        if repository_id:stmt=stmt.where(Issue.repository_id==get_id(repository_id))
        return {'items':[{'id':i.id,'repository_id':i.repository_id,'description':i.description,'expected':i.expected,'observed':i.observed} for i in db.scalars(stmt)]}

def _add_candidate(db,run:RepairRun,replacement:LLMReplacement,model:str,model_usage:dict|None=None) -> dict:
    top={x['path'] for x in run.locations[:10]}
    original,updated,diff=candidate_diff(repo_root(run.repository_id),replacement,top)
    # Serialize per-run candidate admission on PostgreSQL before checking
    # duplicates. SQLite remains supported for single-instance development.
    db.scalar(select(RepairRun.id).where(RepairRun.id == run.id).with_for_update())
    duplicate = db.scalar(select(Candidate.id).where(Candidate.run_id == run.id,
                            Candidate.path == replacement.path, Candidate.updated == updated).limit(1))
    if duplicate is not None:
        raise ValueError('duplicate patch candidate in this repair run')
    identifier=str(uuid.uuid4())
    if replacement.regression_test:
        import ast
        ast.parse(replacement.regression_test,filename='generated_regression.py')
    candidate=Candidate(id=identifier,run_id=run.id,path=replacement.path,original=original,updated=updated,diff=diff,rationale=replacement.rationale,model=model,status='syntax_valid',regression_test=replacement.regression_test,result={'verification':'unproven','existing_tests':'not_run','regression_tests':'not_run','formal_properties':'not_checked',**({'model_usage':model_usage} if model_usage else {})})
    db.add(candidate)
    audit(db,'candidate.created',identifier,run_id=run.id,model=model)
    return {'id':identifier,'path':replacement.path,'diff':diff,'rationale':replacement.rationale,'model':model,'status':'syntax_valid'}

@app.post('/api/repairs',dependencies=[Protect],status_code=201)
def create_repair(request:RepairRequest):
    rid=str(uuid.uuid4())
    with Session.begin() as db:
        issue=db.get(Issue,get_id(request.issue_id))
        if issue is None:raise HTTPException(404,'issue not found')
        entries=index_repository(repo_root(issue.repository_id))
        try: locations=rank(entries,issue.description+' '+issue.expected+' '+issue.observed,request.method,limit=100)
        except (ValueError,KeyError,__import__('httpx').HTTPError) as exc:
            raise HTTPException(503,'ranking unavailable: '+str(exc)[:250]) from exc
        run=RepairRun(id=rid,issue_id=issue.id,repository_id=issue.repository_id,status='localized',method=request.method,locations=locations)
        db.add(run);audit(db,'repair.localized',rid,method=request.method)
    if request.generate:
        return schedule_generation(rid)
    # One stable API schema for both the initial response and subsequent GETs.
    # The React typed client expects repository, issue, method, and timestamps.
    return run_info(run)

def generation_worker(identifier: str, cancel: Event) -> None:
    """Bounded worker with its own SQLAlchemy transaction; no untrusted code execution."""
    try:
        with Session.begin() as db:
            run=get_run(db,identifier)
            if cancel.is_set() or run.status=='cancelled':
                run.status='cancelled'
                return
            run.status='running'
        with Session() as db:
            run=get_run(db,identifier)
            issue=db.get(Issue,run.issue_id)
            entries={e['path']:e for e in index_repository(repo_root(run.repository_id))}
            scoped=[entries[r['path']] for r in run.locations[:5] if r['path'] in entries]
            request_text=issue.description+'\nExpected: '+issue.expected+'\nObserved: '+issue.observed
        try:
            usage:dict={}
            proposals,model=ollama_candidates(request_text,scoped,cancelled=cancel.is_set,usage_sink=usage.update)
        except (ValueError,InterruptedError) as exc:
            with Session.begin() as db:
                run=get_run(db,identifier)
                if run.status!='cancelled':
                    run.status='cancelled' if cancel.is_set() else 'generation_unavailable'
                    run.explanation=str(exc)[:1000]
            return
        with Session.begin() as db:
            run=get_run(db,identifier)
            if cancel.is_set() or run.status=='cancelled':
                run.status='cancelled'
                return
            generated=[];errors=[]
            for repl in proposals:
                try:
                    generated.append(_add_candidate(db,run,repl,model,usage))
                except (ValueError,SyntaxError,UnicodeError) as exc:errors.append(str(exc))
            run.status='generated' if generated else 'generation_failed'
            run.explanation='; '.join(errors)[:1000]
    except Exception as exc:
        with Session.begin() as db:
            run=db.get(RepairRun,identifier)
            if run and run.status!='cancelled':
                run.status='generation_failed'
                run.explanation=(type(exc).__name__+': '+str(exc))[:1000]

def schedule_generation(identifier: str) -> dict:
    identifier=get_id(identifier)
    if not QUEUE_SLOTS.acquire(blocking=False):
        raise HTTPException(429,'bounded repair queue is full')
    try:
        with Session.begin() as db:
            get_run(db,identifier)
            # CAS prevents two concurrent requests from enqueuing the same run.
            changed=db.execute(update(RepairRun).where(RepairRun.id==identifier,
                RepairRun.status.in_(['localized','generation_unavailable','generation_failed','interrupted']))
                .values(status='queued',explanation=''))
            if changed.rowcount!=1:
                raise HTTPException(409,'run is not eligible for generation in current state')
            audit(db,'generation.queued',identifier)
        cancel_event=Event()
        future=EXECUTOR.submit(generation_worker,identifier,cancel_event)
        with JOBS_LOCK:JOBS[identifier]=(future,cancel_event)
        def finished(_: Future) -> None:
            with JOBS_LOCK:
                JOBS.pop(identifier,None)
            QUEUE_SLOTS.release()
        future.add_done_callback(finished)
        return {'id':identifier,'status':'queued','job_id':identifier,'note':'Poll GET /api/jobs/{id} for real execution status'}
    except Exception:
        QUEUE_SLOTS.release()
        raise

@app.post('/api/repairs/{identifier}/generate',dependencies=[Protect],status_code=202)
def generate_candidates(identifier:str):
    return schedule_generation(identifier)

@app.post('/api/repairs/{identifier}/candidates',dependencies=[Protect],status_code=201)
def manual_candidate(identifier:str,payload:ManualCandidate):
    with Session.begin() as db:
        run=get_run(db,identifier)
        try:result=_add_candidate(db,run,LLMReplacement(path=payload.path,old=payload.old,new=payload.new,rationale=payload.rationale,regression_test=payload.regression_test),'manual')
        except (ValueError,SyntaxError,UnicodeError) as exc:raise HTTPException(422,str(exc)) from exc
        run.status='generated'
        return result

@app.get('/api/repairs',dependencies=[Protect])
def repairs(limit:int=Query(default=40,ge=1,le=100)):
    with Session() as db:
        return {'items':[run_info(r) for r in db.scalars(select(RepairRun).order_by(RepairRun.created_at.desc()).limit(limit))]}

@app.get('/api/repairs/{identifier}',dependencies=[Protect])
def repair_details(identifier:str):
    with Session() as db:return run_info(get_run(db,identifier))

@app.get('/api/repairs/{identifier}/candidates',dependencies=[Protect])
def candidates(identifier:str):
    with Session() as db:
        get_run(db,identifier)
        rows=db.scalars(select(Candidate).where(Candidate.run_id==get_id(identifier))).all()
        return {'items':sorted([candidate_info(c) for c in rows],
                               key=lambda candidate:(-candidate['priority']['score'],candidate['id']))}

@app.post('/api/repairs/{identifier}/candidates/{candidate_id}/approve',dependencies=[Protect])
def approve_candidate(identifier: str, candidate_id: str):
    """Approval only authorizes export. Imported repository is never changed."""
    from packages.database import now
    with Session.begin() as db:
        run=get_run(db,identifier)
        candidate=db.get(Candidate,get_id(candidate_id))
        if candidate is None or candidate.run_id!=run.id:
            raise HTTPException(404,'candidate not found in repair run')
        if candidate.approved_at is None:
            candidate.approved_at=now()
            audit(db,'candidate.approved',candidate.id,verification=candidate.result.get('verification','unproven'))
        return {'id':candidate.id,'approved':True,'verified':candidate.result.get('verification','unproven'),
                'disclaimer':'Approval allows exporting the patch; it does not assert correctness.'}

@app.get('/api/repairs/{identifier}/candidates/{candidate_id}/patch',dependencies=[Protect])
def export_patch(identifier: str, candidate_id: str):
    with Session() as db:
        run=get_run(db,identifier)
        candidate=db.get(Candidate,get_id(candidate_id))
        if candidate is None or candidate.run_id!=run.id:
            raise HTTPException(404,'candidate not found in repair run')
        if candidate.approved_at is None:
            raise HTTPException(409,'candidate must be explicitly approved before export')
        return Response(content=candidate.diff,media_type='text/x-diff',headers={
            'Content-Disposition':f'attachment; filename="patchproof-{candidate.id}.patch"',
            'X-PatchProof-Verification':str(candidate.result.get('verification','unproven'))})

@app.post('/api/repairs/{identifier}/verify',dependencies=[Protect],status_code=202)
def verify_repair(identifier: str, candidate_id: str):
    """Queue only. The API has no Docker daemon access or host-execution fallback."""
    with Session.begin() as db:
        run = get_run(db,identifier)
        try:
            job = enqueue(db,run.id,get_id(candidate_id))
        except ValueError as exc:
            raise HTTPException(404,str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(409,str(exc)) from exc
        except OverflowError as exc:
            raise HTTPException(429,str(exc)) from exc
        audit(db,'verification.queued',job.id,candidate_id=job.candidate_id)
        return {'job_id':job.id,'candidate_id':job.candidate_id,'status':'queued',
                'note':'Poll GET /api/jobs/{job_id}. Requires separate trusted sandbox worker.'}

@app.post('/api/repairs/{identifier}/properties',dependencies=[Protect])
def property_check(identifier:str,payload:PropertyRequest):
    with Session() as db:get_run(db,identifier)
    try:return check_linear_int_property(payload.variables,payload.assumptions,payload.conclusion)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc

@app.get('/api/repairs/{identifier}/report',dependencies=[Protect])
def report(identifier:str):
    with Session() as db:
        run=get_run(db,identifier)
        issue=db.get(Issue,run.issue_id)
        rows=db.scalars(select(Candidate).where(Candidate.run_id==run.id)).all()
        content={'schema_version':1,'run':run_info(run),'issue':{'description':issue.description,'expected':issue.expected,'observed':issue.observed},
                 'candidates':sorted([candidate_info(c) for c in rows],
                     key=lambda candidate:(-candidate['priority']['score'],candidate['id'])),
                 'verification_disclaimer':'Passing tests is not formal proof. Source-code correctness remains unproven.'}
        return JSONResponse(content,headers={'Content-Disposition':f'attachment; filename="patchproof-{run.id}.json"'})

@app.get('/api/jobs/{identifier}',dependencies=[Protect])
def job(identifier: str):
    with Session() as db:
        job_id=get_id(identifier)
        record=db.get(VerificationJob,job_id)
        if record:
            return verification_info(record)
        run=get_run(db,identifier)
        return {'id':run.id,'status':run.status,'explanation':run.explanation}

@app.post('/api/jobs/{identifier}/cancel',dependencies=[Protect])
def cancel(identifier: str):
    identifier=get_id(identifier)
    with Session.begin() as db:
        item=db.get(VerificationJob,identifier)
        if item:
            if not cancel_verification(db,item.id):
                raise HTTPException(409,'verification job is already terminal')
            audit(db,'verification.cancelled',identifier)
            return {'id':identifier,'status':'cancelled','note':'Worker polls durable cancellation flag.'}
        run=get_run(db,identifier)
        if run.status not in {'queued','running','localized'}:
            raise HTTPException(409,'job is not cancellable in current state')
        run.status='cancelled'
        audit(db,'repair.cancelled',run.id)
    with JOBS_LOCK:
        current=JOBS.get(identifier)
    if current:
        future,event=current
        event.set()
        future.cancel()
    return {'id':identifier,'status':'cancelled','note':'Model request may require its bounded timeout to stop.'}
