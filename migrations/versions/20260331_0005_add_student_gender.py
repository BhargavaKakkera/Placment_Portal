"""add gender column to student

Revision ID: 20260331_0005
Revises: 20260329_0004
Create Date: 2026-03-31 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260331_0005"
down_revision: Union[str, None] = "20260329_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("student", sa.Column("gender", sa.String(), nullable=True))
    op.execute("UPDATE student SET gender = 'other' WHERE gender IS NULL")
    op.alter_column("student", "gender", existing_type=sa.String(), nullable=False)


def downgrade() -> None:
    op.drop_column("student", "gender")
