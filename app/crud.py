from sqlmodel import Session, select
from .models import User, Student, Company, Job, Application, Offer
from .auth import hash_password, verify_password, create_access_token
from datetime import timedelta
from datetime import datetime
from sqlalchemy import func


APPLICATION_STATUSES = {
    "applied",
    "shortlisted",
    "rejected",
    "offered",
    "accepted",
    "declined",
}


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
    # ensure company is verified before allowing job creation
    company = session.get(Company, company_id)
    if not company or not company.verified:
        raise ValueError("Company not verified or does not exist")
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
    # Eligibility and uniqueness checks
    job = session.get(Job, job_id)
    if not job:
        raise ValueError("Job not found")
    if job.closed:
        raise ValueError("Job is closed")
    if job.application_deadline and job.application_deadline < datetime.utcnow():
        raise ValueError("Application deadline passed")
    statement = select(Application).where(Application.student_id == student_id, Application.job_id == job_id)
    exists = session.exec(statement).first()
    if exists:
        raise ValueError("Already applied to this job")
    student = session.get(Student, student_id)
    if not student:
        raise ValueError("Student not found")
    # student must be verified by admin before applying
    if not getattr(student, 'verified', False):
        raise ValueError("Student profile not verified by admin")
    # CGPA eligibility
    if job.min_cgpa is not None and student.cgpa is not None and student.cgpa < job.min_cgpa:
        raise ValueError("CGPA below eligibility")
    # branch eligibility (simple comma-separated match)
    if job.allowed_branches:
        allowed = [b.strip().lower() for b in job.allowed_branches.split(",") if b.strip()]
        if student.branch and student.branch.lower() not in allowed:
            raise ValueError("Branch not eligible for this job")
    # backlogs
    if job.max_backlogs is not None and student.backlogs is not None and student.backlogs > job.max_backlogs:
        raise ValueError("Too many backlogs to be eligible")
    # placement rule: student who has accepted offer cannot apply
    if student.locked_offer_id is not None:
        raise ValueError("Student already accepted an offer")
    app_obj = Application(student_id=student_id, job_id=job_id)
    session.add(app_obj)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        # likely unique constraint violation
        raise ValueError("Already applied to this job")
    session.refresh(app_obj)
    return app_obj


def create_offer(session: Session, job_id: int, student_id: int, company_id: int, ctc: float) -> Offer:
    # Only allow offers to shortlisted applicants
    statement = select(Application).where(Application.job_id == job_id, Application.student_id == student_id)
    application = session.exec(statement).first()
    if not application:
        raise ValueError("Application not found")
    if application.status != "shortlisted":
        raise ValueError("Can only make offer to shortlisted applicants")
    offer = Offer(job_id=job_id, student_id=student_id, company_id=company_id, ctc=ctc)
    application.status = "offered"
    session.add(offer)
    session.add(application)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        raise ValueError("Unable to create offer (possible duplicate)")
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
    # student must be verified to accept offers
    if not getattr(student, 'verified', False):
        return None
    # perform acceptance atomically: set this offer to accepted, mark student locked,
    # and decline other offers for the student.
    try:
        offer.status = "accepted"
        student.locked_offer_id = offer.id
        session.add(offer)
        session.add(student)
        # decline other offers for this student
        stmt = select(Offer).where(Offer.student_id == student_id, Offer.id != offer_id)
        others = session.exec(stmt).all()
        for o in others:
            if o.status == "offered":
                o.status = "declined"
                session.add(o)
        session.commit()
        session.refresh(offer)
        return offer
    except Exception:
        session.rollback()
        return None


def get_verified_jobs(session: Session, skip: int = 0, limit: int = 10):
    stmt = select(Job).offset(skip).limit(limit)
    return session.exec(stmt).all()


def get_applicants_for_job(session: Session, job_id: int):
    stmt = select(Application).where(Application.job_id == job_id)
    return session.exec(stmt).all()


def shortlist_applicant(session: Session, application_id: int):
    application = session.get(Application, application_id)
    if not application:
        raise ValueError("Application not found")
    application.status = "shortlisted"
    session.add(application)
    session.commit()
    session.refresh(application)
    return application


def reject_applicant(session: Session, application_id: int):
    application = session.get(Application, application_id)
    if not application:
        raise ValueError("Application not found")
    application.status = "rejected"
    session.add(application)
    session.commit()
    session.refresh(application)
    return application


def close_job(session: Session, job_id: int):
    job = session.get(Job, job_id)
    if not job:
        raise ValueError("Job not found")
    job.closed = True
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def list_students(session: Session, skip: int = 0, limit: int = 100, verified: bool = None):
    stmt = select(Student)
    if verified is not None:
        stmt = stmt.where(Student.verified == verified)
    stmt = stmt.offset(skip).limit(limit)
    return session.exec(stmt).all()


def count_students(session: Session, verified: bool = None):
    stmt = select(func.count()).select_from(Student)
    if verified is not None:
        stmt = stmt.where(Student.verified == verified)
    return session.exec(stmt).one()


def list_jobs(session: Session, skip: int = 0, limit: int = 100):
    stmt = select(Job).offset(skip).limit(limit)
    return session.exec(stmt).all()


def list_applications(session: Session, skip: int = 0, limit: int = 100):
    stmt = select(Application).offset(skip).limit(limit)
    return session.exec(stmt).all()


def list_companies(session: Session, skip: int = 0, limit: int = 100, verified: bool = None):
    stmt = select(Company)
    if verified is not None:
        stmt = stmt.where(Company.verified == verified)
    stmt = stmt.offset(skip).limit(limit)
    return session.exec(stmt).all()


def count_companies(session: Session, verified: bool = None):
    stmt = select(func.count()).select_from(Company)
    if verified is not None:
        stmt = stmt.where(Company.verified == verified)
    return session.exec(stmt).one()


def list_users(session: Session, skip: int = 0, limit: int = 100):
    stmt = select(User).offset(skip).limit(limit)
    return session.exec(stmt).all()


def delete_student(session: Session, student_id: int):
    student = session.get(Student, student_id)
    if not student:
        return None
    try:
        session.delete(student)
        session.commit()
        return True
    except Exception:
        session.rollback()
        return None


def delete_company(session: Session, company_id: int):
    company = session.get(Company, company_id)
    if not company:
        return None
    try:
        session.delete(company)
        session.commit()
        return True
    except Exception:
        session.rollback()
        return None


def delete_job(session: Session, job_id: int):
    job = session.get(Job, job_id)
    if not job:
        return None
    try:
        session.delete(job)
        session.commit()
        return True
    except Exception:
        session.rollback()
        return None


def delete_application(session: Session, application_id: int):
    application = session.get(Application, application_id)
    if not application:
        return None
    try:
        session.delete(application)
        session.commit()
        return True
    except Exception:
        session.rollback()
        return None


def withdraw_application(session: Session, application_id: int, student_id: int):
    application = session.get(Application, application_id)
    if not application or application.student_id != student_id:
        return None
    try:
        session.delete(application)
        session.commit()
        return True
    except Exception:
        session.rollback()
        return None


def verify_company(session: Session, company_id: int):
    company = session.get(Company, company_id)
    if not company:
        return None
    company.verified = True
    session.add(company)
    session.commit()
    session.refresh(company)
    return company


def verify_student(session: Session, student_id: int, admin_user_id: int):
    student = session.get(Student, student_id)
    if not student:
        return None
    student.verified = True
    student.verified_at = datetime.utcnow()
    student.verified_by_admin_id = admin_user_id
    session.add(student)
    session.commit()
    session.refresh(student)
    return student


def update_student(session: Session, student_id: int, admin_user_id: int = None, **data):
    student = session.get(Student, student_id)
    if not student:
        return None
    # Apply provided fields
    for key, value in data.items():
        if not hasattr(student, key):
            # ignore unknown fields
            continue
        setattr(student, key, value)

    # If verified explicitly set by admin, update audit fields
    if 'verified' in data and data.get('verified'):
        student.verified_at = datetime.utcnow()
        if admin_user_id is not None:
            student.verified_by_admin_id = admin_user_id

    session.add(student)
    try:
        session.commit()
    except Exception:
        session.rollback()
        return None
    session.refresh(student)
    return student
