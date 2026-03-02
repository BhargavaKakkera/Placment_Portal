from sqlmodel import Session, select
from .models import User, Student, Company, Job, Application, Offer
from .auth import hash_password, verify_password, create_access_token
from datetime import timedelta


def create_user(session: Session, email: str, password: str, role: str) -> User:
    user = User(email=email, password_hash=hash_password(password), role=role)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate_user(session: Session, email: str, password: str):
    statement = select(User).where(User.email == email)
    user = session.exec(statement).first()
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_job(session: Session, company_id: int, **data) -> Job:
    job = Job(company_id=company_id, **data)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def create_student(session: Session, user_id: int, **data) -> Student:
    student = Student(user_id=user_id, **data)
    session.add(student)
    session.commit()
    session.refresh(student)
    return student


def get_student_by_user_id(session: Session, user_id: int):
    statement = select(Student).where(Student.user_id == user_id)
    return session.exec(statement).first()


def create_company(session: Session, user_id: int, name: str) -> Company:
    company = Company(user_id=user_id, name=name)
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


def get_company_by_user_id(session: Session, user_id: int):
    statement = select(Company).where(Company.user_id == user_id)
    return session.exec(statement).first()


def apply_job(session: Session, student_id: int, job_id: int) -> Application:
    # simple uniqueness check
    statement = select(Application).where(Application.student_id == student_id, Application.job_id == job_id)
    exists = session.exec(statement).first()
    if exists:
        return exists
    app = Application(student_id=student_id, job_id=job_id)
    session.add(app)
    session.commit()
    session.refresh(app)
    return app


def create_offer(session: Session, job_id: int, student_id: int, company_id: int, ctc: float) -> Offer:
    offer = Offer(job_id=job_id, student_id=student_id, company_id=company_id, ctc=ctc)
    session.add(offer)
    session.commit()
    session.refresh(offer)
    return offer


def accept_offer(session: Session, offer_id: int, student_id: int):
    # Atomic-ish: check student hasn't locked an offer and offer belongs to student.
    offer = session.get(Offer, offer_id)
    if not offer or offer.student_id != student_id:
        return None
    student = session.get(Student, student_id)
    if student.locked_offer_id is not None:
        return None
    offer.status = "accepted"
    student.locked_offer_id = offer.id
    session.add(offer)
    session.add(student)
    session.commit()
    session.refresh(offer)
    return offer
