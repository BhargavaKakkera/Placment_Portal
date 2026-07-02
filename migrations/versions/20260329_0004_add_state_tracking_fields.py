"""add state tracking fields for lifecycle management

Revision ID: 20260329_0004
Revises: 20260329_0003
Create Date: 2026-03-29 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260329_0004"
down_revision: Union[str, None] = "20260329_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("job", sa.Column("closed_at", sa.DateTime(), nullable=True))
    op.add_column("job", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    
    op.add_column("application", sa.Column("status_reason", sa.String(), nullable=False, server_default="initial"))
    op.add_column("application", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_application_status_reason", "application", ["status_reason"], unique=False)
    
    op.add_column("offer", sa.Column("status_reason", sa.String(), nullable=False, server_default="initial"))
    op.add_column("offer", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_offer_status_reason", "offer", ["status_reason"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_offer_status_reason", table_name="offer")
    op.drop_index("ix_application_status_reason", table_name="application")
    
    op.drop_column("offer", "updated_at")
    op.drop_column("offer", "status_reason")
    
    op.drop_column("application", "updated_at")
    op.drop_column("application", "status_reason")
    
    op.drop_column("job", "updated_at")
    op.drop_column("job", "closed_at")
