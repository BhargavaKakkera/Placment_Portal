"""add token blacklist table for one-time token usage

Revision ID: 20260329_0003
Revises: 20260314_0002
Create Date: 2026-03-29 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260329_0003"
down_revision: Union[str, None] = "20260314_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tokenblacklist",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_purpose", sa.String(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_tokenblacklist_token_hash"),
    )
    op.create_index("ix_tokenblacklist_user_id", "tokenblacklist", ["user_id"], unique=False)
    op.create_index("ix_tokenblacklist_token_purpose", "tokenblacklist", ["token_purpose"], unique=False)


def downgrade() -> None:
    op.drop_table("tokenblacklist")
