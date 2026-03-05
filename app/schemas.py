from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator, field_validator, HttpUrl
from typing import Optional, List
from datetime import datetime

from .enums import Role, Branch, RoleType, ApplicationStatus, OfferStatus


class RegisterIn(BaseModel):

    email: EmailStr = Field(max_length=120)

    password: str = Field(
        min_length=8,
        max_length=100,
        description="Password must be at least 8 characters"
    )

    role: Role


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class StudentCreate(BaseModel):

    name: str = Field(min_length=2, max_length=100)

    roll_no: str = Field(min_length=2, max_length=30)

    cgpa: float = Field(ge=0, le=10)

    branch: Branch

    graduation_year: int = Field(ge=2000, le=2100)

    backlogs: int = Field(ge=0, le=20)

    phone: Optional[str] = Field(
        None,
        min_length=10,
        max_length=15,
        pattern=r"^\+?[0-9]{10,15}$"
    )
    personal_email: Optional[EmailStr] = Field(None, max_length=120)
    address: Optional[str] = Field(None, min_length=5, max_length=300)
    resume_url: Optional[HttpUrl] = None
    github_url: Optional[HttpUrl] = None
    linkedin_url: Optional[HttpUrl] = None
    leetcode_url: Optional[HttpUrl] = None
    codeforces_url: Optional[HttpUrl] = None
    hackerrank_url: Optional[HttpUrl] = None
    portfolio_url: Optional[HttpUrl] = None
    other_coding_url: Optional[HttpUrl] = None

class StudentUpdate(BaseModel):

    name: Optional[str] = Field(
        None,
        min_length=2,
        max_length=100
    )

    phone: Optional[str] = Field(
        None,
        min_length=10,
        max_length=15,
        pattern=r"^\+?[0-9]{10,15}$"
    )

    personal_email: Optional[EmailStr] = Field(
        None,
        max_length=120
    )

    address: Optional[str] = Field(
        None,
        min_length=5,
        max_length=300
    )

    resume_url: Optional[HttpUrl] = None
    github_url: Optional[HttpUrl] = None
    linkedin_url: Optional[HttpUrl] = None
    leetcode_url: Optional[HttpUrl] = None
    codeforces_url: Optional[HttpUrl] = None
    hackerrank_url: Optional[HttpUrl] = None
    portfolio_url: Optional[HttpUrl] = None
    other_coding_url: Optional[HttpUrl] = None


class StudentAdminUpdate(BaseModel):

    roll_no: Optional[str] = Field(None, min_length=2, max_length=30)
    cgpa: Optional[float] = Field(None, ge=0, le=10)
    branch: Optional[Branch]
    graduation_year: Optional[int] = Field(None, ge=2000, le=2100)
    backlogs: Optional[int] = Field(None, ge=0, le=20)

    verified: Optional[bool]


class StudentOut(BaseModel):

    id: int
    user_id: int

    name: str
    roll_no: str

    cgpa: float
    branch: Branch

    graduation_year: int
    backlogs: int

    phone: Optional[str]
    personal_email: Optional[EmailStr]
    address: Optional[str]
    resume_url: Optional[HttpUrl]
    github_url: Optional[HttpUrl]
    linkedin_url: Optional[HttpUrl]
    leetcode_url: Optional[HttpUrl]
    codeforces_url: Optional[HttpUrl]
    hackerrank_url: Optional[HttpUrl]
    portfolio_url: Optional[HttpUrl]
    other_coding_url: Optional[HttpUrl]

    verified: bool
    verified_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)

class CompanyCreate(BaseModel):

    name: str = Field(
        min_length=2,
        max_length=200
    )


class CompanyOut(BaseModel):

    id: int
    user_id: int
    name: str
    verified: bool

    model_config = ConfigDict(from_attributes=True)


class JobCreate(BaseModel):

    title: str = Field(
        min_length=3,
        max_length=150
    )

    description: Optional[str] = Field(
        None,
        min_length=10,
        max_length=3000
    )

    min_cgpa: Optional[float] = Field(None, ge=0, le=10)

    allowed_branches: Optional[List[Branch]] = None

    max_backlogs: Optional[int] = Field(None, ge=0, le=20)

    role_type: RoleType = RoleType.full_time

    internship_duration: Optional[str] = Field(
        None,
        min_length=2,
        max_length=50
    )

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

    @field_validator("allowed_branches", mode="before")
    @classmethod
    def parse_allowed_branches(cls, value):
        if value is None or isinstance(value, list):
            return value
        if isinstance(value, str):
            return [v.strip() for v in value.split(",") if v.strip()]
        return value


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
    
    is_first_admin: bool = False
    verified: bool = False
    verified_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserAdminOut(BaseModel):

    id: int
    email: EmailStr
    role: Role
    
    is_first_admin: bool = False
    verified: bool = False
    verified_at: Optional[datetime] = None
    verified_by_admin_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminVerifyUser(BaseModel):
    """Schema for admin to verify another admin"""
    user_id: int


class PaginationParams(BaseModel):

    skip: int = Field(0, ge=0)

    limit: int = Field(
        10,
        ge=1,
        le=100
    )


class AdminDashboardResponse(BaseModel):
    """Schema for admin dashboard statistics."""
    total_students: int
    placed_students: int
    active_jobs: int
    total_companies: int
    offers_made: int
    offers_accepted: int
