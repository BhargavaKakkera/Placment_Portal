from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
from sqlalchemy import UniqueConstraint

from .enums import (
    Role,
    Branch,
    RoleType,
    ApplicationStatus,
    OfferStatus
)


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    role: Role
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Student(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    user_id: int = Field(foreign_key="user.id", unique=True)

    name: str
    roll_no: str

    cgpa: float
    branch: Branch

    graduation_year: int
    backlogs: int = 0

    # ---- personal info ----

    phone: Optional[str] = None
    personal_email: Optional[str] = None
    address: Optional[str] = None
    resume_url: Optional[str] = None

    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    leetcode_url: Optional[str] = None
    codeforces_url: Optional[str] = None
    hackerrank_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    other_coding_url: Optional[str] = None

    # ---- placement verification ----
    verified: bool = Field(default=False)
    verified_at: Optional[datetime] = None
    verified_by_admin_id: Optional[int] = Field(default=None, foreign_key="user.id")

    locked_offer_id: Optional[int] = Field(default=None, foreign_key="offer.id")


class Company(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    user_id: int = Field(foreign_key="user.id", unique=True)

    name: str
    verified: bool = Field(default=False)


class Job(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    company_id: int = Field(foreign_key="company.id")

    title: str
    description: Optional[str] = None

    min_cgpa: Optional[float] = None

    # CSV storage: "CSE,ECE"
    # None means ALL branches allowed
    allowed_branches: Optional[str] = None

    max_backlogs: Optional[int] = None

    role_type: RoleType = Field(default=RoleType.full_time)

    internship_duration: Optional[str] = None
    stipend: Optional[float] = None

    ctc: Optional[float] = None

    ppo_available: bool = Field(default=False)

    application_deadline: Optional[datetime] = None

    closed: bool = Field(default=False)

    created_at: datetime = Field(default_factory=datetime.utcnow)


class Application(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    student_id: int = Field(foreign_key="student.id")
    job_id: int = Field(foreign_key="job.id")

    applied_at: datetime = Field(default_factory=datetime.utcnow)

    status: ApplicationStatus = Field(default=ApplicationStatus.applied)

    __table_args__ = (
        UniqueConstraint("student_id", "job_id", name="u_student_job"),
    )


class Offer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    job_id: int = Field(foreign_key="job.id")
    student_id: int = Field(foreign_key="student.id")
    company_id: int = Field(foreign_key="company.id")

    ctc: Optional[float] = None

    status: OfferStatus = Field(default=OfferStatus.offered)

    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("job_id", "student_id", name="u_job_student_offer"),
    )
