"""add email verification fields to user

Revision ID: 20260314_0002
Revises: 20260307_0001
Create Date: 2026-03-14 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260314_0002"
down_revision: Union[str, None] = "20260307_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    op.add_column(
        "user",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "user",
        sa.Column("email_verified_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_user_email_verified", "user", ["email_verified"], unique=False)

    op.execute(
        sa.text(
            """
            UPDATE "user"
            SET email_verified = TRUE,
                email_verified_at = COALESCE(email_verified_at, created_at)
            WHERE role = 'student'
            """
        )
    )
    if not is_sqlite:
        op.alter_column("user", "email_verified", server_default=None)

def downgrade() -> None:
    op.drop_index("ix_user_email_verified", table_name="user")
    op.drop_column("user", "email_verified_at")
    op.drop_column("user", "email_verified")
