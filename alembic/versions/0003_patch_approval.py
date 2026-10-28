"""Explicit patch approval, distinct from verification result.

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("candidates", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))

def downgrade():
    op.drop_column("candidates", "approved_at")
