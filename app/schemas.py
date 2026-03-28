from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator, field_validator, HttpUrl
from typing import Optional, List
from datetime import datetime
import re

from .enums import (
    Role,
    Branch,
    RoleType,
    ApplicationStatus,
    OfferStatus,
    CompanyApplicationAction,
)


class RegisterIn(BaseModel):

    email: EmailStr = Field(max_length=120)

    password: str = Field(
        min_length=8,
        max_length=100,
        description="Password must be at least 8 characters with uppercase, lowercase, and digit"
    )

    role: Role

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """
        Validate password meets complexity requirements.

        Args:
            v: Password to validate

        Returns:
            Validated password

        Raises:
            ValueError: If password doesn't meet requirements
        """
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterOut(BaseModel):
    message: str
    email_verification_sent: bool
    verification_token: Optional[str] = None


class PasswordResetRequestIn(BaseModel):
    email: EmailStr = Field(max_length=120)


class EmailVerificationConfirmIn(BaseModel):
    token: str = Field(min_length=20)


class EmailVerificationRequestIn(BaseModel):
    email: EmailStr = Field(max_length=120)



class PasswordResetConfirmIn(BaseModel):
    token: str = Field(min_length=20)
    new_password: str = Field(
        min_length=8,
        max_length=100,
        description="Password must be at least 8 characters",
    )


class StudentUpdate(BaseModel):
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


class AdminStudentProvisionIn(BaseModel):
    email: EmailStr = Field(max_length=120)
    name: str = Field(min_length=2, max_length=100)
    reg_no: str = Field(min_length=2, max_length=30)
    roll_no: str = Field(min_length=2, max_length=30)
    cgpa: float = Field(ge=0, le=10)
    branch: Branch
    graduation_year: int = Field(ge=2000, le=2100)
    backlogs: int = Field(default=0, ge=0, le=20)

    @model_validator(mode="after")
    def _validate_number_fields(self):
        if self.reg_no == self.roll_no:
            raise ValueError("reg_no and roll_no must be different")
        return self


class AdminStudentProvisionOut(BaseModel):
    user_id: int
    student_id: int
    invite_token: Optional[str] = None
    invite_sent: bool
    message: str


class StudentAdminUpdate(BaseModel):

    reg_no: Optional[str] = Field(None, min_length=2, max_length=30)
    roll_no: Optional[str] = Field(None, min_length=2, max_length=30)
    cgpa: Optional[float] = Field(None, ge=0, le=10)
    branch: Optional[Branch]
    graduation_year: Optional[int] = Field(None, ge=2000, le=2100)
    backlogs: Optional[int] = Field(None, ge=0, le=20)

class StudentOut(BaseModel):

    id: int
    user_id: int

    name: str
    reg_no: str
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

            if self.internship_duration is None or not self.internship_duration.strip():
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


class ApplicationListOut(BaseModel):
    items: List[ApplicationOut]
    skip: int
    limit: int
    total: int
    has_more: bool


class StudentApplicationItemOut(BaseModel):
    id: int
    job_id: int
    company_id: int
    company_name: str
    company_active: bool = True
    job_title: str
    job_description: Optional[str]
    applied_at: datetime
    status: ApplicationStatus


class StudentApplicationListOut(BaseModel):
    items: List[StudentApplicationItemOut]
    skip: int
    limit: int
    total: int
    has_more: bool


class CompanyApplicantItemOut(BaseModel):
    id: int
    student_id: int
    student_name: str
    reg_no: str
    roll_no: str
    branch: Branch
    cgpa: float
    graduation_year: int
    backlogs: int
    resume_url: Optional[HttpUrl]
    applied_at: datetime
    status: ApplicationStatus


class CompanyApplicantListOut(BaseModel):
    items: List[CompanyApplicantItemOut]
    skip: int
    limit: int
    total: int
    has_more: bool


class CompanyApplicationStatusUpdate(BaseModel):
    status: CompanyApplicationAction
    ctc: Optional[float] = Field(
        default=None,
        ge=0,
        description="Required when status is offered for full-time jobs"
    )
    offer_response_deadline: Optional[datetime] = Field(
        default=None,
        description="Deadline until which student can accept an offered application"
    )


class OfferOut(BaseModel):

    id: int
    job_id: int
    student_id: int
    company_id: int

    ctc: Optional[float]

    status: OfferStatus
    response_deadline: Optional[datetime]

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StudentOfferItemOut(BaseModel):
    id: int
    job_id: int
    company_id: int
    company_name: str
    company_active: bool = True
    job_title: str
    job_description: Optional[str]
    role_type: RoleType
    stipend: Optional[float]
    ctc: Optional[float]
    status: OfferStatus
    response_deadline: Optional[datetime]
    created_at: datetime


class CompanyAcceptedOfferItemOut(BaseModel):
    id: int
    job_id: int
    student_id: int
    student_name: str
    reg_no: str
    roll_no: str
    job_title: str
    role_type: RoleType
    stipend: Optional[float]
    ctc: Optional[float]
    status: OfferStatus
    created_at: datetime


class CompanyAcceptedOfferListOut(BaseModel):
    items: List[CompanyAcceptedOfferItemOut]
    skip: int
    limit: int
    total: int
    has_more: bool


class UserOut(BaseModel):

    id: int
    email: EmailStr
    role: Role
    email_verified: bool = False
    email_verified_at: Optional[datetime] = None
    
    is_first_admin: bool = False
    verified: bool = False
    verified_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserAdminOut(BaseModel):

    id: int
    email: EmailStr
    role: Role
    email_verified: bool = False
    email_verified_at: Optional[datetime] = None
    
    is_first_admin: bool = False
    verified: bool = False
    verified_at: Optional[datetime] = None
    verified_by_admin_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserAdminListOut(BaseModel):
    items: List[UserAdminOut]
    skip: int
    limit: int
    total: int
    has_more: bool


class StudentListOut(BaseModel):
    items: List[StudentOut]
    skip: int
    limit: int
    total: int
    has_more: bool


class CompanyListOut(BaseModel):
    items: List[CompanyOut]
    skip: int
    limit: int
    total: int
    has_more: bool


class JobListOut(BaseModel):
    items: List[JobOut]
    skip: int
    limit: int
    total: int
    has_more: bool


class BranchPlacementStatOut(BaseModel):
    branch: Branch
    total_students: int
    placed_students: int
    placement_rate: float


class AdminVerifyUser(BaseModel):
    """Schema for admin to verify another admin"""
    user_id: int


class PaginationParams(BaseModel):
    skip: int = Field(
        0,
        ge=0,
        description="Number of records to skip before returning items",
    )
    limit: int = Field(
        10,
        ge=1,
        le=100,
        description="Maximum number of records to return",
    )


class AdminDashboardResponse(BaseModel):
    """Schema for admin dashboard statistics."""
    total_students: int
    placed_students: int
    placement_rate: float
    branch_stats: List[BranchPlacementStatOut]
    active_jobs: int
    total_jobs: int
    total_companies: int
    pending_companies: int
    pending_admins: int
    offers_made: int
    offers_pending_response: int
    offers_accepted: int
