from sqlmodel import SQLModel, Field, Relationship
from typing import Optional, List
from datetime import datetime
from enum import Enum as PyEnum


class Role(str, PyEnum):
    student = "student"
    company = "company"
    admin = "admin"


class ApplicationStatus(str, PyEnum):
    APPLIED = "applied"
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"
    OFFERED = "offered"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class OfferStatus(str, PyEnum):
    OFFERED = "offered"
    ACCEPTED = "accepted"
    DECLINED = "declined"


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
    roll_no: Optional[str] = None
    cgpa: Optional[float] = None
    branch: Optional[str] = None
    graduation_year: Optional[int] = None
    backlogs: Optional[int] = 0
    locked_offer_id: Optional[int] = None


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
    allowed_branches: Optional[str] = None  # comma-separated for simple demo
    max_backlogs: Optional[int] = None
    application_deadline: Optional[datetime] = None
    closed: bool = Field(default=False)  # admin/company can close
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Application(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="student.id")
    job_id: int = Field(foreign_key="job.id")
    applied_at: datetime = Field(default_factory=datetime.utcnow)
    status: ApplicationStatus = Field(default=ApplicationStatus.APPLIED.value)


class Offer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="job.id")
    student_id: int = Field(foreign_key="student.id")
    company_id: int = Field(foreign_key="company.id")
    ctc: Optional[float] = None
    status: OfferStatus = Field(default=OfferStatus.OFFERED.value)
    created_at: datetime = Field(default_factory=datetime.utcnow)
