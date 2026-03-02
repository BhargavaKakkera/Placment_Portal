from pydantic import BaseModel, EmailStr
from typing import Optional


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


class StudentCreate(BaseModel):
    name: str
    roll_no: Optional[str] = None
    cgpa: Optional[float] = None
    branch: Optional[str] = None
    graduation_year: Optional[int] = None
    backlogs: Optional[int] = 0


class CompanyCreate(BaseModel):
    name: str

