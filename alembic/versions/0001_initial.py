"""Initial persistence schema.

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa
revision='0001'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('repositories',sa.Column('id',sa.String(36),primary_key=True),sa.Column('name',sa.String(256),nullable=False),sa.Column('digest',sa.String(64),nullable=False),sa.Column('status',sa.String(30)),sa.Column('file_count',sa.Integer()),sa.Column('indexed',sa.JSON()),sa.Column('created_at',sa.DateTime(timezone=True)))
    op.create_index('ix_repositories_digest','repositories',['digest'],unique=True)
    op.create_table('issues',sa.Column('id',sa.String(36),primary_key=True),sa.Column('repository_id',sa.String(36),sa.ForeignKey('repositories.id')),sa.Column('description',sa.Text(),nullable=False),sa.Column('expected',sa.Text()),sa.Column('observed',sa.Text()),sa.Column('created_at',sa.DateTime(timezone=True)))
    op.create_index('ix_issues_repository_id','issues',['repository_id'])
    op.create_table('repair_runs',sa.Column('id',sa.String(36),primary_key=True),sa.Column('repository_id',sa.String(36),sa.ForeignKey('repositories.id')),sa.Column('issue_id',sa.String(36),sa.ForeignKey('issues.id')),sa.Column('status',sa.String(32)),sa.Column('method',sa.String(20)),sa.Column('locations',sa.JSON()),sa.Column('explanation',sa.Text()),sa.Column('created_at',sa.DateTime(timezone=True)))
    op.create_index('ix_repair_runs_repository_id','repair_runs',['repository_id'])
    op.create_index('ix_repair_runs_issue_id','repair_runs',['issue_id'])
    op.create_table('candidates',sa.Column('id',sa.String(36),primary_key=True),sa.Column('run_id',sa.String(36),sa.ForeignKey('repair_runs.id')),sa.Column('path',sa.String(512)),sa.Column('original',sa.Text()),sa.Column('updated',sa.Text()),sa.Column('diff',sa.Text()),sa.Column('rationale',sa.Text()),sa.Column('model',sa.String(100)),sa.Column('status',sa.String(32)),sa.Column('result',sa.JSON()))
    op.create_index('ix_candidates_run_id','candidates',['run_id'])
    op.create_table('audit_events',sa.Column('id',sa.Integer(),primary_key=True,autoincrement=True),sa.Column('action',sa.String(60)),sa.Column('object_id',sa.String(36)),sa.Column('detail',sa.JSON()),sa.Column('created_at',sa.DateTime(timezone=True)))
    op.create_index('ix_audit_events_object_id','audit_events',['object_id'])

def downgrade():
    for table in ('audit_events','candidates','repair_runs','issues','repositories'):
        op.drop_table(table)
