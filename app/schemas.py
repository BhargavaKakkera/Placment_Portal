from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator, field_validator, HttpUrl, computed_field
from pydantic_core import PydanticCustomError
from typing import Optional, List, Any
from datetime import datetime
import re

from .enums import (
    Role,
    Branch,
    Gender,
    RoleType,
    ApplicationStatus,
    ApplicationStatusReason,
    OfferStatus,
    OfferStatusReason,
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
        description="Password must be at least 8 characters with uppercase, lowercase, and digit"
    )

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password meets complexity requirements."""
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class ChangePasswordIn(BaseModel):
    old_password: str = Field(
        min_length=8,
        max_length=100,
        description="Current password"
    )
    new_password: str = Field(
        min_length=8,
        max_length=100,
        description="New password must be at least 8 characters with uppercase, lowercase, and digit"
    )

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password meets complexity requirements."""
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class StudentUpdate(BaseModel):
    """Only student-editable fields."""
    phone: Optional[str] = Field(
        None,
        description="Phone number must be exactly 10 digits"
    )

    personal_email: Optional[EmailStr] = Field(
        None,
        max_length=120
    )

    cgpa: Optional[float] = Field(None, ge=0.0, le=10.0)
    backlogs: Optional[int] = Field(None, ge=0, le=8)

    address: Optional[str] = Field(
        None,
        min_length=5,
        max_length=300
    )

    resume_url: Optional[str] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    leetcode_url: Optional[str] = None
    codeforces_url: Optional[str] = None
    hackerrank_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    other_coding_url: Optional[str] = None

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v):
        """Convert empty strings to None and validate non-empty values."""
        if isinstance(v, str) and v.strip() == "":
            return None
        if v is None:
            return None
        value = str(v).strip()
        if not value.isdigit() or len(value) != 10:
            raise PydanticCustomError(
                "phone_number",
                "Phone number must be exactly 10 digits",
            )
        return value

    @field_validator("personal_email", mode="before")
    @classmethod
    def validate_personal_email(cls, v):
        """Convert empty strings to None."""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("address", mode="before")
    @classmethod
    def validate_address(cls, v):
        """Convert empty strings to None."""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("resume_url", "github_url", "linkedin_url", "leetcode_url", "codeforces_url", "hackerrank_url", "portfolio_url", "other_coding_url", mode="before")
    @classmethod
    def validate_urls(cls, v):
        """Convert empty strings to None for URL fields."""
        if v is None:
            return None
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("github_url", mode="after")
    @classmethod
    def validate_github(cls, v: Optional[str]) -> Optional[str]:
        """GitHub URL must point to valid profile if provided."""
        if v and "github.com" not in str(v):
            raise ValueError("GitHub URL must be from github.com")
        return v

    @field_validator("linkedin_url", mode="after")
    @classmethod
    def validate_linkedin(cls, v: Optional[str]) -> Optional[str]:
        """LinkedIn URL must be from LinkedIn if provided."""
        if v and "linkedin.com" not in str(v):
            raise ValueError("LinkedIn URL must be from linkedin.com")
        return v


class AdminStudentProvisionIn(BaseModel):
    """Admin creating student accounts."""
    email: EmailStr = Field(max_length=120)
    name: str = Field(min_length=2, max_length=100)
    reg_no: str = Field(min_length=2, max_length=30)
    roll_no: str = Field(min_length=2, max_length=30)
    cgpa: float = Field(ge=0.0, le=10.0)
    branch: Branch
    gender: Gender
    graduation_year: int = Field(ge=2026, le=2030)
    backlogs: int = Field(default=0, ge=0, le=8)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Name must be alphabetic (with spaces/hyphens)."""
        if not all(c.isalpha() or c in " -'" for c in v):
            raise ValueError("Name must contain only letters, spaces, hyphens, or apostrophes")
        return v.strip()

    @field_validator("reg_no", "roll_no")
    @classmethod
    def validate_unique_numbers(cls, v: str) -> str:
        """Registration/Roll numbers must be non-empty."""
        if not v or not v.strip():
            raise ValueError("Cannot be empty")
        return v.strip().upper()

    @field_validator("graduation_year")
    @classmethod
    def validate_graduation(cls, v: int) -> int:
        """Graduation year must be reasonable."""
        current_year = datetime.utcnow().year
        if v < current_year:
            raise ValueError("Student must not be already graduated")
        if v > current_year + 5:
            raise ValueError("Graduation year must be within 5 years")
        return v

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
    """Admin-editable student fields with validation."""
    reg_no: Optional[str] = Field(None, min_length=2, max_length=30)
    roll_no: Optional[str] = Field(None, min_length=2, max_length=30)
    cgpa: Optional[float] = Field(None, ge=0.0, le=10.0)
    branch: Optional[Branch]
    gender: Optional[Gender]
    graduation_year: Optional[int] = Field(None, ge=2026, le=2030)
    backlogs: Optional[int] = Field(None, ge=0, le=8)

    @field_validator("graduation_year")
    @classmethod
    def validate_graduation(cls, v: Optional[int]) -> Optional[int]:
        """Graduation year must be reasonable."""
        if v:
            current_year = datetime.utcnow().year
            if v < current_year:
                raise ValueError("Student must not be already graduated")
            if v > current_year + 5:
                raise ValueError("Graduation year must be within 5 years")
        return v

class StudentOut(BaseModel):

    id: int
    user_id: int

    name: str
    reg_no: str
    roll_no: str

    cgpa: float
    branch: Branch
    gender: Gender

    graduation_year: int
    backlogs: int

    phone: Optional[str]
    personal_email: Optional[EmailStr]
    address: Optional[str]
    resume_url: Optional[str]
    github_url: Optional[str]
    linkedin_url: Optional[str]
    leetcode_url: Optional[str]
    codeforces_url: Optional[str]
    hackerrank_url: Optional[str]
    portfolio_url: Optional[str]
    other_coding_url: Optional[str]
    
    is_active: bool = True

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

    min_cgpa: Optional[float] = Field(None, ge=0.0, le=10.0)

    allowed_branches: Optional[List[Branch]] = None

    max_backlogs: Optional[int] = Field(None, ge=0, le=8)

    role_type: RoleType = RoleType.full_time

    internship_duration: Optional[str] = Field(
        None,
        min_length=2,
        max_length=50
    )

    stipend: Optional[float] = Field(None, ge=0)  # Max ₹200k/month

    ctc: Optional[float] = Field(None, ge=0)  # Annual amount

    ppo_available: Optional[bool] = False

    application_deadline: Optional[datetime] = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Reject titles that are too generic."""
        generic_titles = {"job", "position", "role", "offer"}
        if v.lower().strip() in generic_titles:
            raise ValueError("Job title must be specific (e.g., 'Senior Software Engineer')")
        return v.strip()

    @field_validator("application_deadline")
    @classmethod
    def validate_deadline(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Deadline must be in future."""
        if v:
            from .datetime_utils import utc_now
            if v <= utc_now():
                raise ValueError("Application deadline must be in the future")
        return v

    @field_validator("ctc")
    @classmethod
    def validate_ctc(cls, v: Optional[float]) -> Optional[float]:
        """CTC must be a positive annual amount."""
        if v is not None and v <= 0:
            raise PydanticCustomError(
                "ctc_positive",
                "CTC must be greater than 0",
            )
        return v

    @field_validator("stipend")
    @classmethod
    def validate_stipend(cls, v: Optional[float]) -> Optional[float]:
        """Stipend must be reasonable."""
        if v is not None and v <= 0:
                raise PydanticCustomError(
                "stipend_positive",
                "stipend must be greater than 0",
            )
        return v

    @field_validator("allowed_branches")
    @classmethod
    def validate_branches(cls, v: Optional[List[Branch]]) -> Optional[List[Branch]]:
        """Validate branch list."""
        if v is not None and len(v) == 0:
            raise ValueError("At least one branch must be selected or leave empty for all branches")
        return v

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


class JobDeadlineUpdate(BaseModel):
    """Update application deadline for a job."""
    application_deadline: Optional[datetime] = Field(
        None,
        description="New application deadline (or None to remove deadline)"
    )

    @field_validator("application_deadline")
    @classmethod
    def validate_deadline(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Deadline must be in future if provided.
        
        Note: datetime-local input comes as naive datetime in user's local timezone.
        We assume it's already in UTC (as per backend convention), so direct comparison is valid.
        """
        if v:
            from .datetime_utils import utc_now
            # Deadline must be strictly in the future
            if v <= utc_now():
                raise ValueError("Application deadline must be in the future")
        return v


class JobOut(BaseModel):

    id: int
    company_id: int
    company_name: Optional[str] = None
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
    role_type: RoleType
    ctc: Optional[float] = None
    stipend: Optional[float] = None
    internship_duration: Optional[str] = None
    ppo_available: bool = False
    application_deadline: Optional[datetime] = None
    min_cgpa: Optional[float] = None
    max_backlogs: Optional[int] = None
    created_at: Optional[datetime] = None
    applied_at: datetime
    status: ApplicationStatus
    status_reason: Optional[ApplicationStatusReason] = None


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
    gender: Gender
    cgpa: float
    graduation_year: int
    backlogs: int
    resume_url: Optional[HttpUrl]
    applied_at: datetime
    status: ApplicationStatus
    # Personal details for display in modals
    phone: Optional[str] = None
    personal_email: Optional[EmailStr] = None
    address: Optional[str] = None
    github_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    leetcode_url: Optional[str] = None
    codeforces_url: Optional[str] = None
    hackerrank_url: Optional[str] = None
    portfolio_url: Optional[str] = None
    other_coding_url: Optional[str] = None


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
    job_description: Optional[str] = None
    role_type: RoleType
    stipend: Optional[float] = None
    ctc: Optional[float] = None
    ppo_available: bool = False
    internship_duration: Optional[str] = None
    status: OfferStatus
    status_reason: Optional[OfferStatusReason] = None
    response_deadline: Optional[datetime] = None
    created_at: datetime


class StudentOfferListOut(BaseModel):
    items: List[StudentOfferItemOut]
    skip: int
    limit: int
    total: int
    has_more: bool


class CompanyAcceptedOfferItemOut(BaseModel):
    id: int
    job_id: int
    student_id: int
    student_name: str
    student_reg_no: str
    reg_no: Optional[str] = None
    roll_no: Optional[str] = None
    job_title: str
    job_description: Optional[str] = None
    role_type: RoleType
    stipend: Optional[float] = None
    ctc: Optional[float] = None
    ppo_available: bool = False
    internship_duration: Optional[str] = None
    response_deadline: Optional[datetime] = None
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
    """Safe pagination parameters with hard limits."""
    skip: int = Field(
        0,
        ge=0,
        le=10000,
        description="Number of records to skip before returning items",
    )
    limit: int = Field(
        20,
        ge=1,
        le=100,
        description="Maximum number of records to return",
    )


class PaginationMeta(BaseModel):
    """Consistent pagination metadata for all list endpoints."""
    skip: int
    limit: int
    total: int
    has_more: bool
    
    @computed_field
    @property
    def current_page(self) -> int:
        """Calculated page number (1-indexed)."""
        return (self.skip // self.limit) + 1 if self.limit > 0 else 1
    
    @computed_field
    @property
    def total_pages(self) -> int:
        """Total number of pages."""
        return (self.total + self.limit - 1) // self.limit if self.limit > 0 else 1


class ErrorResponse(BaseModel):
    """Standard error response for all API endpoints."""
    success: bool = False
    error: str
    error_code: str
    details: Optional[dict] = None
    request_id: Optional[str] = None


class SuccessResponse(BaseModel):
    """Standard success response wrapper."""
    success: bool = True
    data: Any = None
    message: Optional[str] = None


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
