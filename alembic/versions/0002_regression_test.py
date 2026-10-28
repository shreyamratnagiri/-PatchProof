"""Add generated regression test source with explicit verification evidence.

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa
revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('candidates',sa.Column('regression_test',sa.Text(),nullable=False,server_default=''))

def downgrade():
    op.drop_column('candidates','regression_test')
