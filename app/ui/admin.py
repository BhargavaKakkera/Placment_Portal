import secrets

from fastapi import APIRouter, Request
from pydantic import ValidationError
from sqlmodel import Session, select

from .. import crud
from ..auth import create_password_reset_token, hash_password
from ..database import engine
from ..enums import Branch, Role
from ..models import Student, User
from ..schemas import AdminStudentProvisionIn, StudentAdminUpdate
from .helpers import home_for, redirect_path, redirect_to, render, require_user, txt, validation_message

router = APIRouter(prefix="/admin")


@router.get("", name="ui_admin_dashboard")
def admin_dashboard(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        stats = {
            "total_students": crud.count_students(session),
            "placed_students": crud.count_placed_students(session),
            "active_jobs": crud.count_active_jobs(session),
            "total_jobs": crud.count_jobs(session),
            "total_companies": crud.count_companies(session, verified=True),
            "pending_companies": crud.count_companies(session, verified=False),
            "pending_admins": crud.count_pending_admins(session),
            "offers_made": crud.count_offers_made(session),
            "offers_pending_response": crud.count_offers_pending_response(session),
            "offers_accepted": crud.count_offers_accepted(session),
            "branch_stats": crud.get_branch_placement_stats(session),
        }
        return render(request, "admin_dashboard.html", current_user=user, role_home=home_for(user), stats=stats)


@router.get("/users", name="ui_admin_users")
def admin_users_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        return render(request, "admin_users.html", current_user=user, role_home=home_for(user), users=crud.get_all_users(session, 0, 100))


@router.get("/users/{user_id}", name="ui_admin_user_detail")
def admin_user_detail_page(user_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        detail = crud.get_user_by_id(session, user_id)
        if not detail:
            return redirect_to(request, "ui_admin_users", "User not found.", "warning")
        return render(request, "admin_user_detail.html", current_user=user, role_home=home_for(user), user_detail=detail)


@router.get("/pending-admins", name="ui_admin_pending_admins")
def admin_pending_admins_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not user.is_first_admin:
            return redirect_to(request, "ui_admin_dashboard", "Only the first admin can verify pending admins.", "warning")
        return render(request, "admin_pending_admins.html", current_user=user, role_home=home_for(user), pending_admins=crud.get_pending_admins(session, 0, 100))


@router.post("/users/{user_id}/verify-admin", name="ui_admin_verify_admin")
def admin_verify_admin_submit(user_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not user.is_first_admin:
            return redirect_to(request, "ui_admin_dashboard", "Only the first admin can verify admins.", "warning")
        if not crud.verify_admin(session, user_id, user.id):
            return redirect_to(request, "ui_admin_pending_admins", "Could not verify admin.", "danger")
    return redirect_to(request, "ui_admin_pending_admins", "Admin verified.", "success")


@router.get("/students", name="ui_admin_students")
def admin_students_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        return render(request, "admin_students.html", current_user=user, role_home=home_for(user), students=crud.list_students(session, 0, 100, include_inactive=True))


@router.post("/students/provision", name="ui_admin_students_provision")
async def admin_students_provision_submit(request: Request):
    form = await request.form()
    try:
        payload = AdminStudentProvisionIn.model_validate(
            {
                "email": str(form.get("email", "")).strip(),
                "name": str(form.get("name", "")).strip(),
                "reg_no": str(form.get("reg_no", "")).strip(),
                "roll_no": str(form.get("roll_no", "")).strip(),
                "cgpa": form.get("cgpa"),
                "branch": str(form.get("branch", Branch.CSE.value)),
                "graduation_year": form.get("graduation_year"),
                "backlogs": form.get("backlogs", 0),
            }
        )
    except (ValidationError, ValueError) as exc:
        return redirect_to(request, "ui_admin_students", validation_message(exc), "warning")
    email = payload.email
    reg_no = payload.reg_no
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        crud.purge_expired_unverified_users(session, older_than_days=15, email=email)
        if crud.get_user_by_email(session, email):
            return redirect_to(request, "ui_admin_students", "Email already registered.", "warning")
        if session.exec(select(Student).where(Student.reg_no == reg_no)).first():
            return redirect_to(request, "ui_admin_students", "Registration number already exists.", "warning")
        temp_password = secrets.token_urlsafe(24)
        try:
            new_user = User(
                email=email,
                password_hash=hash_password(temp_password),
                role=Role.student,
                email_verified=False,
                is_first_admin=False,
                verified=False,
                is_active=True,
            )
            session.add(new_user)
            session.flush()
            student = Student(
                user_id=new_user.id,
                name=payload.name,
                reg_no=reg_no,
                roll_no=payload.roll_no,
                cgpa=payload.cgpa,
                branch=payload.branch,
                graduation_year=payload.graduation_year,
                backlogs=payload.backlogs,
            )
            session.add(student)
            session.commit()
        except Exception:
            session.rollback()
            return redirect_to(request, "ui_admin_students", "Could not provision student.", "danger")
    return redirect_to(request, "ui_admin_students", f"Student provisioned. Demo invite token: {create_password_reset_token(new_user.id)}", "success")


@router.get("/students/{student_id}", name="ui_admin_student_edit")
def admin_student_edit_page(student_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        student = session.get(Student, student_id)
        if not student:
            return redirect_to(request, "ui_admin_students", "Student not found.", "warning")
        return render(request, "admin_student_edit.html", current_user=user, role_home=home_for(user), student=student)


@router.post("/students/{student_id}", name="ui_admin_student_edit_post")
async def admin_student_edit_submit(student_id: int, request: Request):
    form = await request.form()
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        try:
            payload = StudentAdminUpdate.model_validate(
                {
                    "reg_no": txt(form.get("reg_no")),
                    "roll_no": txt(form.get("roll_no")),
                    "cgpa": form.get("cgpa") if txt(form.get("cgpa")) is not None else None,
                    "branch": str(form.get("branch", Branch.CSE.value)),
                    "graduation_year": form.get("graduation_year") if txt(form.get("graduation_year")) is not None else None,
                    "backlogs": form.get("backlogs") if txt(form.get("backlogs")) is not None else None,
                }
            )
        except (ValidationError, ValueError) as exc:
            return redirect_path(request, f"/ui/admin/students/{student_id}", validation_message(exc), "warning")
        updated = crud.update_student(
            session,
            student_id,
            **payload.model_dump(mode="json", exclude_unset=True)
        )
        if not updated:
            return redirect_path(request, f"/ui/admin/students/{student_id}", "Could not update student.", "danger")
    return redirect_to(request, "ui_admin_students", "Student updated.", "success")


@router.post("/students/{student_id}/delete", name="ui_admin_student_delete")
def admin_student_delete_submit(student_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not crud.delete_student(session, student_id):
            return redirect_to(request, "ui_admin_students", "Could not deactivate student.", "danger")
    return redirect_to(request, "ui_admin_students", "Student deactivated.", "info")


@router.post("/students/{student_id}/reactivate", name="ui_admin_student_reactivate")
def admin_student_reactivate_submit(student_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not crud.reactivate_student(session, student_id):
            return redirect_to(request, "ui_admin_students", "Could not reactivate student.", "danger")
    return redirect_to(request, "ui_admin_students", "Student reactivated.", "success")


@router.get("/companies", name="ui_admin_companies")
def admin_companies_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        return render(request, "admin_companies.html", current_user=user, role_home=home_for(user), companies=crud.list_companies(session, 0, 100, include_inactive=True))


@router.post("/companies/{company_id}/verify", name="ui_admin_company_verify")
def admin_company_verify_submit(company_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not crud.verify_company(session, company_id):
            return redirect_to(request, "ui_admin_companies", "Could not verify company.", "danger")
    return redirect_to(request, "ui_admin_companies", "Company verified.", "success")


@router.post("/companies/{company_id}/delete", name="ui_admin_company_delete")
def admin_company_delete_submit(company_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not crud.delete_company(session, company_id):
            return redirect_to(request, "ui_admin_companies", "Could not deactivate company.", "danger")
    return redirect_to(request, "ui_admin_companies", "Company deactivated.", "info")


@router.post("/companies/{company_id}/reactivate", name="ui_admin_company_reactivate")
def admin_company_reactivate_submit(company_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not crud.reactivate_company(session, company_id):
            return redirect_to(request, "ui_admin_companies", "Could not reactivate company.", "danger")
    return redirect_to(request, "ui_admin_companies", "Company reactivated.", "success")


@router.get("/jobs", name="ui_admin_jobs")
def admin_jobs_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        return render(request, "admin_jobs.html", current_user=user, role_home=home_for(user), jobs=crud.list_jobs(session, 0, 100))


@router.post("/jobs/{job_id}/close", name="ui_admin_job_close")
def admin_job_close_submit(job_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        try:
            crud.close_job(session, job_id)
        except ValueError as exc:
            return redirect_to(request, "ui_admin_jobs", str(exc), "warning")
    return redirect_to(request, "ui_admin_jobs", "Job closed.", "info")


@router.post("/jobs/{job_id}/delete", name="ui_admin_job_delete")
def admin_job_delete_submit(job_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        try:
            ok = crud.delete_job(session, job_id)
        except ValueError as exc:
            return redirect_to(request, "ui_admin_jobs", str(exc), "warning")
        if not ok:
            return redirect_to(request, "ui_admin_jobs", "Could not delete job.", "danger")
    return redirect_to(request, "ui_admin_jobs", "Job deleted.", "info")


@router.get("/applications", name="ui_admin_applications")
def admin_applications_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        return render(request, "admin_applications.html", current_user=user, role_home=home_for(user), applications=crud.list_applications(session, 0, 100))


@router.post("/applications/{application_id}/delete", name="ui_admin_application_delete")
def admin_application_delete_submit(application_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not crud.delete_application(session, application_id):
            return redirect_to(request, "ui_admin_applications", "Could not delete application.", "danger")
    return redirect_to(request, "ui_admin_applications", "Application deleted.", "info")
