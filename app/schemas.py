from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    role: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class JobCreate(BaseModel):
    title: str
    description: Optional[str] = None
    min_cgpa: Optional[float] = None
    allowed_branches: Optional[str] = None
    max_backlogs: Optional[int] = None
    application_deadline: Optional[datetime] = None


class StudentCreate(BaseModel):
    name: str
    roll_no: Optional[str] = None
    cgpa: Optional[float] = None
    branch: Optional[str] = None
    graduation_year: Optional[int] = None
    backlogs: Optional[int] = 0


class CompanyCreate(BaseModel):
    name: str


class StudentUpdate(BaseModel):
    name: Optional[str] = None
    roll_no: Optional[str] = None
    cgpa: Optional[float] = None
    branch: Optional[str] = None
    graduation_year: Optional[int] = None
    backlogs: Optional[int] = None
    verified: Optional[bool] = None


class UserOut(BaseModel):
    id: int
    email: EmailStr
    role: str


class StudentOut(BaseModel):
    id: int
    user_id: int
    name: str
    roll_no: Optional[str]
    cgpa: Optional[float]
    branch: Optional[str]
    graduation_year: Optional[int]
    backlogs: Optional[int]
    verified: bool
    verified_at: Optional[datetime]



class CompanyOut(BaseModel):
    id: int
    user_id: int
    name: str
    verified: bool


class JobOut(BaseModel):
    id: int
    company_id: int
    title: str
    description: Optional[str]
    min_cgpa: Optional[float]
    allowed_branches: Optional[str]
    max_backlogs: Optional[int]
    application_deadline: Optional[datetime]
    closed: bool
    created_at: datetime


class ApplicationOut(BaseModel):
    id: int
    student_id: int
    job_id: int
    applied_at: datetime
    status: str


class OfferOut(BaseModel):
    id: int
    job_id: int
    student_id: int
    company_id: int
    ctc: Optional[float]
    status: str
    created_at: datetime


class PaginationParams(BaseModel):
    skip: int = Field(0, ge=0)
    limit: int = Field(10, ge=1, le=100)

