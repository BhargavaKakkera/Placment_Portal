from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from ..database import get_session
from .. import crud
from ..schemas import RegisterIn, Token
from ..auth import create_access_token
from ..models import User
from ..enums import Role

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token)
def register(payload: RegisterIn, session: Session = Depends(get_session)):
    is_first_admin = False
    try:
        # Serialize admin registration in SQLite to avoid multiple "first admin" users.
        if payload.role == Role.admin:
            session.exec(text("BEGIN IMMEDIATE"))
            existing_admin = session.exec(
                select(User).where(User.role == Role.admin)
            ).first()
            is_first_admin = existing_admin is None

        existing = session.exec(select(User).where(User.email == payload.email)).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        user = crud.create_user(
            session,
            payload.email,
            payload.password,
            payload.role,
            is_first_admin=is_first_admin
        )
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=400, detail="Email already registered")

    token = create_access_token({"user_id": user.id, "role": user.role})
    return {"access_token": token}


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    user = crud.authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect credentials")
    
    # Check if admin needs verification
    if user.role == Role.admin:
        # First admin is always verified
        if not user.is_first_admin and not user.verified:
            raise HTTPException(
                status_code=403, 
                detail="Admin not verified. Please wait for approval from first admin."
            )
    
    token = create_access_token({"user_id": user.id, "role": user.role})
    return {"access_token": token}
