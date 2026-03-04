from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator
from typing import Optional, List
from datetime import datetime

from .enums import (
    Role,
    Branch,
    RoleType,
    ApplicationStatus,
    OfferStatus
)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: Role


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class StudentCreate(BaseModel):
    name: str
    roll_no: Optional[str] = None
    cgpa: Optional[float] = Field(None, ge=0, le=10)
    branch: Optional[Branch] = None
    graduation_year: Optional[int] = None
    backlogs: Optional[int] = Field(0, ge=0)


class StudentUpdate(BaseModel):
    name: Optional[str] = None
    roll_no: Optional[str] = None
    cgpa: Optional[float] = Field(None, ge=0, le=10)
    branch: Optional[Branch] = None
    graduation_year: Optional[int] = None
    backlogs: Optional[int] = Field(None, ge=0)
    verified: Optional[bool] = None


class StudentOut(BaseModel):

    id: int
    user_id: int
    name: str
    roll_no: Optional[str]
    cgpa: Optional[float]
    branch: Optional[Branch]
    graduation_year: Optional[int]
    backlogs: Optional[int]
    verified: bool
    verified_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class CompanyCreate(BaseModel):
    name: str


class CompanyOut(BaseModel):

    id: int
    user_id: int
    name: str
    verified: bool

    model_config = ConfigDict(from_attributes=True)


class JobCreate(BaseModel):

    title: str = Field(..., min_length=3, max_length=120)

    description: Optional[str] = Field(
        None,
        min_length=10,
        max_length=2000
    )

    min_cgpa: Optional[float] = Field(None, ge=0, le=10)

    # None means ALL branches allowed
    allowed_branches: Optional[List[Branch]] = Field(
        None,
        description="None means all branches allowed"
    )

    max_backlogs: Optional[int] = Field(None, ge=0)

    role_type: RoleType = RoleType.full_time

    internship_duration: Optional[str] = None
    stipend: Optional[float] = Field(None, ge=0)

    ctc: Optional[float] = Field(None, ge=0)

    ppo_available: Optional[bool] = False

    application_deadline: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_job_fields(self):

        if self.role_type == RoleType.internship:

            if self.stipend is None:
                raise ValueError("Internship must include stipend")

            if self.internship_duration is None:
                raise ValueError("Internship must include duration")

        if self.role_type == RoleType.full_time:

            if self.ctc is None:
                raise ValueError("Full-time role must include CTC")

        return self


class JobOut(BaseModel):

    id: int
    company_id: int
    title: str
    description: Optional[str]

    min_cgpa: Optional[float]
    allowed_branches: Optional[List[Branch]]
    max_backlogs: Optional[int]

    role_type: RoleType

    internship_duration: Optional[str]
    stipend: Optional[float]

    ctc: Optional[float]

    ppo_available: bool
    application_deadline: Optional[datetime]

    closed: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplicationOut(BaseModel):

    id: int
    student_id: int
    job_id: int
    applied_at: datetime
    status: ApplicationStatus

    model_config = ConfigDict(from_attributes=True)


class OfferOut(BaseModel):

    id: int
    job_id: int
    student_id: int
    company_id: int
    ctc: Optional[float]
    status: OfferStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserOut(BaseModel):

    id: int
    email: EmailStr
    role: Role

    model_config = ConfigDict(from_attributes=True)


class PaginationParams(BaseModel):
    skip: int = Field(0, ge=0)
    limit: int = Field(10, ge=1, le=100)