"""Durable sandbox verification jobs; independent trusted worker.

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision='0004'
down_revision='0003'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('verification_jobs',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('run_id',sa.String(36),sa.ForeignKey('repair_runs.id'),nullable=False),
        sa.Column('candidate_id',sa.String(36),sa.ForeignKey('candidates.id'),nullable=False),
        sa.Column('status',sa.String(30),nullable=False),
        sa.Column('worker_id',sa.String(100)),
        sa.Column('lease_until',sa.DateTime(timezone=True)),
        sa.Column('started_at',sa.DateTime(timezone=True)),
        sa.Column('completed_at',sa.DateTime(timezone=True)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('result',sa.JSON(),nullable=False))
    for field in ('run_id','candidate_id','status'):
        op.create_index('ix_verification_jobs_'+field,'verification_jobs',[field])

def downgrade():
    op.drop_table('verification_jobs')
