"""initial schema

Revision ID: 20260307_0001
Revises:
Create Date: 2026-03-07 00:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260307_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("is_first_admin", sa.Boolean(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("verified_at", sa.DateTime(), nullable=True),
        sa.Column("verified_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["verified_by_admin_id"], ["user.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_email", "user", ["email"], unique=True)
    op.create_index("ix_user_is_active", "user", ["is_active"], unique=False)
    op.create_index("ix_user_role", "user", ["role"], unique=False)
    op.create_index("ix_user_verified", "user", ["verified"], unique=False)

    op.create_table(
        "company",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_company_is_active", "company", ["is_active"], unique=False)
    op.create_index("ix_company_verified", "company", ["verified"], unique=False)

    op.create_table(
        "job",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("min_cgpa", sa.Float(), nullable=True),
        sa.Column("allowed_branches", sa.String(), nullable=True),
        sa.Column("max_backlogs", sa.Integer(), nullable=True),
        sa.Column("role_type", sa.String(), nullable=False),
        sa.Column("internship_duration", sa.String(), nullable=True),
        sa.Column("stipend", sa.Float(), nullable=True),
        sa.Column("ctc", sa.Float(), nullable=True),
        sa.Column("ppo_available", sa.Boolean(), nullable=False),
        sa.Column("application_deadline", sa.DateTime(), nullable=True),
        sa.Column("closed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_application_deadline", "job", ["application_deadline"], unique=False)
    op.create_index("ix_job_closed", "job", ["closed"], unique=False)
    op.create_index("ix_job_company_id", "job", ["company_id"], unique=False)
    op.create_index("ix_job_role_type", "job", ["role_type"], unique=False)

    op.create_table(
        "student",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("reg_no", sa.String(), nullable=False),
        sa.Column("roll_no", sa.String(), nullable=False),
        sa.Column("cgpa", sa.Float(), nullable=False),
        sa.Column("branch", sa.String(), nullable=False),
        sa.Column("graduation_year", sa.Integer(), nullable=False),
        sa.Column("backlogs", sa.Integer(), nullable=False),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("personal_email", sa.String(), nullable=True),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("resume_url", sa.String(), nullable=True),
        sa.Column("github_url", sa.String(), nullable=True),
        sa.Column("linkedin_url", sa.String(), nullable=True),
        sa.Column("leetcode_url", sa.String(), nullable=True),
        sa.Column("codeforces_url", sa.String(), nullable=True),
        sa.Column("hackerrank_url", sa.String(), nullable=True),
        sa.Column("portfolio_url", sa.String(), nullable=True),
        sa.Column("other_coding_url", sa.String(), nullable=True),
        sa.Column("locked_offer_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("deactivated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_student_reg_no", "student", ["reg_no"], unique=True)
    op.create_index("ix_student_is_active", "student", ["is_active"], unique=False)

    op.create_table(
        "application",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["job_id"], ["job.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "job_id", name="u_student_job"),
    )
    op.create_index("ix_application_job_id", "application", ["job_id"], unique=False)
    op.create_index("ix_application_status", "application", ["status"], unique=False)
    op.create_index("ix_application_student_id", "application", ["student_id"], unique=False)

    op.create_table(
        "offer",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("student_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("ctc", sa.Float(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("response_deadline", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["job.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["student_id"], ["student.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "student_id", name="u_job_student_offer"),
    )
    op.create_index("ix_offer_company_id", "offer", ["company_id"], unique=False)
    op.create_index("ix_offer_job_id", "offer", ["job_id"], unique=False)
    op.create_index("ix_offer_response_deadline", "offer", ["response_deadline"], unique=False)
    op.create_index("ix_offer_status", "offer", ["status"], unique=False)
    op.create_index("ix_offer_student_id", "offer", ["student_id"], unique=False)
    op.create_foreign_key(
        "fk_student_locked_offer_id_offer",
        "student",
        "offer",
        ["locked_offer_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    if is_sqlite:
        op.execute("PRAGMA foreign_keys=OFF")
    op.drop_constraint("fk_student_locked_offer_id_offer", "student", type_="foreignkey")
    op.drop_index("ix_offer_student_id", table_name="offer")
    op.drop_index("ix_offer_status", table_name="offer")
    op.drop_index("ix_offer_response_deadline", table_name="offer")
    op.drop_index("ix_offer_job_id", table_name="offer")
    op.drop_index("ix_offer_company_id", table_name="offer")
    op.drop_table("offer")

    op.drop_index("ix_application_student_id", table_name="application")
    op.drop_index("ix_application_status", table_name="application")
    op.drop_index("ix_application_job_id", table_name="application")
    op.drop_table("application")

    op.drop_index("ix_student_reg_no", table_name="student")
    op.drop_index("ix_student_is_active", table_name="student")
    op.drop_table("student")

    op.drop_index("ix_job_role_type", table_name="job")
    op.drop_index("ix_job_company_id", table_name="job")
    op.drop_index("ix_job_closed", table_name="job")
    op.drop_index("ix_job_application_deadline", table_name="job")
    op.drop_table("job")

    op.drop_index("ix_company_verified", table_name="company")
    op.drop_index("ix_company_is_active", table_name="company")
    op.drop_table("company")

    op.drop_index("ix_user_verified", table_name="user")
    op.drop_index("ix_user_role", table_name="user")
    op.drop_index("ix_user_is_active", table_name="user")
    op.drop_index("ix_user_email", table_name="user")
    op.drop_table("user")
    if is_sqlite:
        op.execute("PRAGMA foreign_keys=ON")
