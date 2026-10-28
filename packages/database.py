"""Transactional repository and repair persistence; defaults to SQLite for local smoke tests.
Use PATCHPROOF_DATABASE_URL=postgresql+psycopg://... for deployment.
"""
from __future__ import annotations
import os
from datetime import datetime, timezone
from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

class Base(DeclarativeBase):
    pass

def now() -> datetime:
    return datetime.now(timezone.utc)

class Repository(Base):
    __tablename__ = 'repositories'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    digest: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default='indexed')
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    indexed: Mapped[dict] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Issue(Base):
    __tablename__ = 'issues'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey('repositories.id'), index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    expected: Mapped[str] = mapped_column(Text, default='')
    observed: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class RepairRun(Base):
    __tablename__ = 'repair_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    repository_id: Mapped[str] = mapped_column(ForeignKey('repositories.id'), index=True)
    issue_id: Mapped[str] = mapped_column(ForeignKey('issues.id'), index=True)
    status: Mapped[str] = mapped_column(String(32), default='pending')
    method: Mapped[str] = mapped_column(String(20), default='lexical')
    locations: Mapped[list] = mapped_column(JSON, default=list)
    explanation: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Candidate(Base):
    __tablename__ = 'candidates'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('repair_runs.id'), index=True)
    path: Mapped[str] = mapped_column(String(512))
    original: Mapped[str] = mapped_column(Text)
    updated: Mapped[str] = mapped_column(Text)
    diff: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(100), default='manual')
    status: Mapped[str] = mapped_column(String(32), default='syntax_valid')
    regression_test: Mapped[str] = mapped_column(Text, default='')
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
    result: Mapped[dict] = mapped_column(JSON, default=dict)

class VerificationJob(Base):
    __tablename__ = 'verification_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey('repair_runs.id'), nullable=False, index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey('candidates.id'), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='queued', index=True)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

class AuditEvent(Base):
    __tablename__ = 'audit_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[str] = mapped_column(String(60))
    object_id: Mapped[str] = mapped_column(String(36), index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

engine = create_engine(os.environ.get('PATCHPROOF_DATABASE_URL', 'sqlite:///./patchproof.db'), pool_pre_ping=True)
Session = sessionmaker(bind=engine, expire_on_commit=False)

def init_db() -> None:
    Base.metadata.create_all(engine)
