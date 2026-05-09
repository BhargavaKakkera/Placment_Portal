import secrets

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import ValidationError
from sqlmodel import Session, select, func

from .. import crud
from ..auth import create_password_reset_token, hash_password
from ..config import DEBUG
from ..database import engine
from ..email_service import send_student_invite_email
from ..enums import Branch, Gender, Role
from ..models import Student, User, Company, Job, Application, Offer
from ..schemas import AdminStudentProvisionIn, StudentAdminUpdate
from ..crud.state_transitions import count_valid_offers
from .helpers import build_pager, extract_field_errors, home_for, parse_page_limit, read_form_with_csrf, redirect_path, redirect_to, render, require_user, txt, validation_message

router = APIRouter(prefix="/admin")
DEBUG_MODE = DEBUG


@router.get("", name="ui_admin_dashboard")
def admin_dashboard(request: Request):
    new_user_id = None
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
        recent_rows = crud.list_jobs(session, 0, 5)
        companies_by_id = {company.id: company for company in crud.list_companies(session, 0, 1000, include_inactive=True)}
        recent_jobs = [
            {
                "title": job.title,
                "role_type": job.role_type,
                "ctc": job.ctc,
                "stipend": job.stipend,
                "internship_duration": job.internship_duration,
                "ppo_available": job.ppo_available,
                "allowed_branches": job.allowed_branches,
                "company_name": companies_by_id.get(job.company_id).name if companies_by_id.get(job.company_id) else None,
            }
            for job in recent_rows
        ]
        return render(
            request,
            "admin_dashboard.html",
            current_user=user,
            role_home=home_for(user),
            stats=stats,
            recent_jobs=recent_jobs,
        )


@router.get("/users", name="ui_admin_users")
def admin_users_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        page, limit, skip = parse_page_limit(request, default_limit=20, max_limit=100)
        users = crud.get_all_users(session, skip, limit)
        total = crud.count_users(session)
        pager = build_pager(request, total=total, page=page, limit=limit)
        return render(
            request,
            "admin_users.html",
            current_user=user,
            role_home=home_for(user),
            users=users,
            pager=pager,
        )


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
        page, limit, skip = parse_page_limit(request, default_limit=20, max_limit=100)
        pending_admins = crud.get_pending_admins(session, skip, limit)
        total = crud.count_pending_admins(session)
        pager = build_pager(request, total=total, page=page, limit=limit)
        return render(
            request,
            "admin_pending_admins.html",
            current_user=user,
            role_home=home_for(user),
            pending_admins=pending_admins,
            pager=pager,
        )


@router.post("/users/{user_id}/verify-admin", name="ui_admin_verify_admin")
async def admin_verify_admin_submit(user_id: int, request: Request):
    try:
        await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_admin_pending_admins", str(exc), "warning")
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
    branch_raw = txt(request.query_params.get("branch"))
    reg_no_filter = txt(request.query_params.get("reg_no"))
    branch_filter = None
    if branch_raw:
        try:
            branch_filter = Branch(branch_raw)
        except ValueError:
            branch_filter = None

    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        page, limit, skip = parse_page_limit(request, default_limit=20, max_limit=100)
        students = crud.list_students(
            session,
            skip,
            limit,
            branch=branch_filter,
            reg_no=reg_no_filter,
            include_inactive=True,
        )
        total = crud.count_students(
            session,
            branch=branch_filter,
            reg_no=reg_no_filter,
            include_inactive=True,
        )
        pager = build_pager(request, total=total, page=page, limit=limit)
        return render(
            request,
            "admin_students.html",
            current_user=user,
            role_home=home_for(user),
            students=students,
            Gender=Gender,
            form_data={},
            field_errors={},
            error_message=None,
            branch_filter=branch_raw or "",
            reg_no_filter=reg_no_filter or "",
            pager=pager,
        )


@router.post("/students/provision", name="ui_admin_students_provision")
async def admin_students_provision_submit(request: Request, background_tasks: BackgroundTasks):
    try:
        form = await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_admin_students", str(exc), "warning")
    
    # Prepare form data
    form_data = {
        "email": str(form.get("email", "")).strip(),
        "name": str(form.get("name", "")).strip(),
        "reg_no": str(form.get("reg_no", "")).strip(),
        "roll_no": str(form.get("roll_no", "")).strip(),
        "cgpa": form.get("cgpa", ""),
        "branch": str(form.get("branch", Branch.CSE.value)),
        "gender": txt(form.get("gender")) or "",
        "graduation_year": form.get("graduation_year", ""),
        "backlogs": form.get("backlogs", "0"),
    }
    
    try:
        payload = AdminStudentProvisionIn.model_validate(
            {
                "email": form_data["email"],
                "name": form_data["name"],
                "reg_no": form_data["reg_no"],
                "roll_no": form_data["roll_no"],
                "cgpa": form_data["cgpa"],
                "branch": form_data["branch"],
                "gender": form_data["gender"] or None,
                "graduation_year": form_data["graduation_year"],
                "backlogs": form_data["backlogs"],
            }
        )
    except (ValidationError, ValueError) as exc:
        with Session(engine) as session:
            user, redirect = require_user(request, session, Role.admin, verified_admin=True)
            if redirect:
                return redirect
            students = crud.list_students(session, 0, 100, include_inactive=True)
        field_errors = extract_field_errors(exc)
        return render(
            request,
            "admin_students.html",
            current_user=user,
            role_home=home_for(user),
            students=students,
            Gender=Gender,
            form_data=form_data,
            field_errors=field_errors,
            error_message=validation_message(exc),
        )
    email = payload.email
    reg_no = payload.reg_no
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        crud.purge_expired_unverified_users(session, older_than_days=15, email=email)
        if crud.get_user_by_email(session, email):
            students = crud.list_students(session, 0, 100, include_inactive=True)
            return render(
                request,
                "admin_students.html",
                current_user=user,
                role_home=home_for(user),
                students=students,
                Gender=Gender,
                form_data=form_data,
                field_errors={},
                error_message="Email already registered.",
            )
        if session.exec(select(Student).where(Student.reg_no == reg_no)).first():
            students = crud.list_students(session, 0, 100, include_inactive=True)
            return render(
                request,
                "admin_students.html",
                current_user=user,
                role_home=home_for(user),
                students=students,
                Gender=Gender,
                form_data=form_data,
                field_errors={},
                error_message="Registration number already exists.",
            )
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
                gender=payload.gender,
                graduation_year=payload.graduation_year,
                backlogs=payload.backlogs,
            )
            session.add(student)
            session.commit()
            new_user_id = new_user.id
        except Exception:
            session.rollback()
            students = crud.list_students(session, 0, 100, include_inactive=True)
            return render(
                request,
                "admin_students.html",
                current_user=user,
                role_home=home_for(user),
                students=students,
                Gender=Gender,
                form_data=form_data,
                field_errors={},
                error_message="Could not provision student.",
            )
    if not new_user_id:
        return redirect_to(request, "ui_admin_students", "Could not provision student.", "danger")
    invite_token = create_password_reset_token(new_user_id)
    background_tasks.add_task(send_student_invite_email, str(email), invite_token)
    if DEBUG_MODE:
        return redirect_to(
            request,
            "ui_admin_students",
            f"Student provisioned. Demo invite token: {invite_token}",
            "success",
        )
    return redirect_to(
        request,
        "ui_admin_students",
        "Student provisioned and invite instructions generated.",
        "success",
    )


@router.get("/students/{student_id}", name="ui_admin_student_edit")
def admin_student_edit_page(student_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        student = session.get(Student, student_id)
        if not student:
            return redirect_to(request, "ui_admin_students", "Student not found.", "warning")
        return render(
            request,
            "admin_student_edit.html",
            current_user=user,
            role_home=home_for(user),
            Gender=Gender,
            student=student,
            form_data={},
            field_errors={},
            error_message=None,
        )


@router.post("/students/{student_id}", name="ui_admin_student_edit_post")
async def admin_student_edit_submit(student_id: int, request: Request):
    try:
        form = await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_path(request, f"/ui/admin/students/{student_id}", str(exc), "warning")
    
    # Prepare form data
    form_data = {
        "reg_no": txt(form.get("reg_no")) or "",
        "roll_no": txt(form.get("roll_no")) or "",
        "cgpa": form.get("cgpa", ""),
        "branch": str(form.get("branch", Branch.CSE.value)),
        "gender": txt(form.get("gender")) or "",
        "graduation_year": form.get("graduation_year", ""),
        "backlogs": form.get("backlogs", ""),
    }
    
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        student = session.get(Student, student_id)
        if not student:
            return redirect_to(request, "ui_admin_students", "Student not found.", "warning")
        try:
            payload = StudentAdminUpdate.model_validate(
                {
                    "reg_no": txt(form.get("reg_no")),
                    "roll_no": txt(form.get("roll_no")),
                    "cgpa": form.get("cgpa") if txt(form.get("cgpa")) is not None else None,
                    "branch": form_data["branch"],
                    "gender": form_data["gender"] or None,
                    "graduation_year": form.get("graduation_year") if txt(form.get("graduation_year")) is not None else None,
                    "backlogs": form.get("backlogs") if txt(form.get("backlogs")) is not None else None,
                }
            )
        except (ValidationError, ValueError) as exc:
            field_errors = extract_field_errors(exc)
            return render(
                request,
                "admin_student_edit.html",
                current_user=user,
                role_home=home_for(user),
                Gender=Gender,
                student=student,
                form_data=form_data,
                field_errors=field_errors,
                error_message=validation_message(exc),
            )
        try:
            updated = crud.update_student(
                session,
                student_id,
                **payload.model_dump(mode="json", exclude_unset=True)
            )
        except ValueError as exc:
            # Handle constraint violations from update_student
            return render(
                request,
                "admin_student_edit.html",
                current_user=user,
                role_home=home_for(user),
                Gender=Gender,
                student=student,
                form_data=form_data,
                field_errors={},
                error_message=str(exc),
            )
        if not updated:
            field_errors = {}
            return render(
                request,
                "admin_student_edit.html",
                current_user=user,
                role_home=home_for(user),
                Gender=Gender,
                student=student,
                form_data=form_data,
                field_errors=field_errors,
                error_message="Could not update student.",
            )
    return redirect_to(request, "ui_admin_students", "Student updated.", "success")


@router.post("/students/{student_id}/delete", name="ui_admin_student_delete")
async def admin_student_delete_submit(student_id: int, request: Request):
    try:
        await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_admin_students", str(exc), "warning")
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        try:
            crud.delete_student(session, student_id)
        except ValueError as exc:
            return redirect_to(request, "ui_admin_students", str(exc), "danger")
    return redirect_to(request, "ui_admin_students", "Student deactivated.", "info")


@router.post("/students/{student_id}/reactivate", name="ui_admin_student_reactivate")
async def admin_student_reactivate_submit(student_id: int, request: Request):
    try:
        await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_admin_students", str(exc), "warning")
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        result = crud.reactivate_student(session, student_id)
        if result is None:
            return redirect_to(request, "ui_admin_students", "Student not found.", "danger")
        if result is not True:
            return redirect_to(request, "ui_admin_students", "Could not reactivate student.", "danger")
    return redirect_to(request, "ui_admin_students", "Student reactivated.", "success")


@router.get("/companies", name="ui_admin_companies")
def admin_companies_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        page, limit, skip = parse_page_limit(request, default_limit=20, max_limit=100)
        companies = crud.list_companies(session, skip, limit, include_inactive=True)
        total = crud.count_companies(session, include_inactive=True)
        pager = build_pager(request, total=total, page=page, limit=limit)
        return render(
            request,
            "admin_companies.html",
            current_user=user,
            role_home=home_for(user),
            companies=companies,
            pager=pager,
        )


@router.post("/companies/{company_id}/verify", name="ui_admin_company_verify")
async def admin_company_verify_submit(company_id: int, request: Request):
    try:
        await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_admin_companies", str(exc), "warning")
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not crud.verify_company(session, company_id):
            return redirect_to(request, "ui_admin_companies", "Could not verify company.", "danger")
    return redirect_to(request, "ui_admin_companies", "Company verified.", "success")


@router.post("/companies/{company_id}/delete", name="ui_admin_company_delete")
async def admin_company_delete_submit(company_id: int, request: Request):
    try:
        await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_admin_companies", str(exc), "warning")
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not crud.delete_company(session, company_id):
            return redirect_to(request, "ui_admin_companies", "Could not deactivate company.", "danger")
    return redirect_to(request, "ui_admin_companies", "Company deactivated.", "info")


@router.post("/companies/{company_id}/reactivate", name="ui_admin_company_reactivate")
async def admin_company_reactivate_submit(company_id: int, request: Request):
    try:
        await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_admin_companies", str(exc), "warning")
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not crud.reactivate_company(session, company_id):
            return redirect_to(request, "ui_admin_companies", "Could not reactivate company.", "danger")
    return redirect_to(request, "ui_admin_companies", "Company reactivated.", "success")


@router.get("/jobs", name="ui_admin_jobs")
def admin_jobs_page(request: Request):
    job_id_raw = txt(request.query_params.get("job_id"))
    company_id_raw = txt(request.query_params.get("company_id"))
    company_name_filter = txt(request.query_params.get("company_name"))
    
    job_id_filter = None
    if job_id_raw:
        try:
            job_id_filter = int(job_id_raw)
        except ValueError:
            job_id_filter = None
    
    company_id_filter = None
    if company_id_raw:
        try:
            company_id_filter = int(company_id_raw)
        except ValueError:
            company_id_filter = None

    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        page, limit, skip = parse_page_limit(request, default_limit=20, max_limit=100)
        jobs = crud.list_jobs(
            session,
            skip,
            limit,
            company_id=company_id_filter,
            company_name=company_name_filter,
            job_id=job_id_filter,
        )
        total = crud.count_jobs(
            session,
            company_id=company_id_filter,
            company_name=company_name_filter,
            job_id=job_id_filter,
        )
        pager = build_pager(request, total=total, page=page, limit=limit)
        companies_by_id = {company.id: company for company in crud.list_companies(session, 0, 1000, include_inactive=True)}
        return render(
            request,
            "admin_jobs.html",
            current_user=user,
            role_home=home_for(user),
            jobs=jobs,
            companies_by_id=companies_by_id,
            job_id_filter=job_id_raw or "",
            company_id_filter=company_id_raw or "",
            company_name_filter=company_name_filter or "",
            pager=pager,
        )


@router.post("/jobs/{job_id}/close", name="ui_admin_job_close")
async def admin_job_close_submit(job_id: int, request: Request):
    try:
        await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_admin_jobs", str(exc), "warning")
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
async def admin_job_delete_submit(job_id: int, request: Request):
    try:
        await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_admin_jobs", str(exc), "warning")
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
        page, limit, skip = parse_page_limit(request, default_limit=20, max_limit=100)
        applications = crud.list_applications(session, skip, limit)
        total = crud.count_applications(session)
        pager = build_pager(request, total=total, page=page, limit=limit)
        return render(
            request,
            "admin_applications.html",
            current_user=user,
            role_home=home_for(user),
            applications=applications,
            pager=pager,
        )


@router.get("/offers", name="ui_admin_offers")
def admin_offers_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        page, limit, skip = parse_page_limit(request, default_limit=20, max_limit=100)
        offers = crud.list_offers_admin_summaries(session, skip, limit)
        total = crud.count_offers_all(session)
        pager = build_pager(request, total=total, page=page, limit=limit)
        return render(
            request,
            "admin_offers.html",
            current_user=user,
            role_home=home_for(user),
            offers=offers,
            pager=pager,
        )


@router.post("/offers/{offer_id}/delete", name="ui_admin_offer_delete")
async def admin_offer_delete_submit(offer_id: int, request: Request):
    try:
        await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_admin_offers", str(exc), "warning")
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not crud.admin_delete_offer(session, offer_id):
            return redirect_to(request, "ui_admin_offers", "Offer not found or could not be deleted.", "danger")
    return redirect_to(request, "ui_admin_offers", "Offer deleted. Student is unlocked if it was accepted.", "success")


@router.post("/applications/{application_id}/delete", name="ui_admin_application_delete")
async def admin_application_delete_submit(application_id: int, request: Request):
    try:
        await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_admin_applications", str(exc), "warning")
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        if not crud.delete_application(session, application_id):
            return redirect_to(request, "ui_admin_applications", "Could not delete application.", "danger")
    return redirect_to(request, "ui_admin_applications", "Application deleted.", "info")


@router.get("/analytics", name="ui_admin_analytics")
def admin_analytics_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.admin, verified_admin=True)
        if redirect:
            return redirect
        
        # Calculate summary metrics
        total_students = crud.count_students(session)
        placed_students = crud.count_placed_students(session)
        placement_rate = (placed_students / total_students * 100) if total_students > 0 else 0
        
        # CTC statistics
        offers_stmt = select(Offer).where(Offer.status == "accepted")
        accepted_offers = session.exec(offers_stmt).all()
        
        ctc_values = []
        for offer in accepted_offers:
            job = session.get(Job, offer.job_id)
            if job and job.ctc:
                ctc_values.append(job.ctc)
        
        average_ctc = sum(ctc_values) / len(ctc_values) if ctc_values else 0
        highest_ctc = max(ctc_values) if ctc_values else 0
        lowest_ctc = min(ctc_values) if ctc_values else 0
        total_offers = len(accepted_offers)
        
        summary = {
            "total_students": total_students,
            "placed_students": placed_students,
            "placement_rate": placement_rate,
            "average_ctc": average_ctc,
            "highest_ctc": highest_ctc,
            "lowest_ctc": lowest_ctc,
            "total_offers": total_offers,
        }
        
        # Branch-wise statistics
        branch_stats = crud.get_branch_placement_stats(session)
        
        # Company-wise statistics
        company_metrics = []
        companies_stmt = select(Company).where(Company.is_active == True)
        companies = session.exec(companies_stmt).all()
        
        for company in companies:
            offers_made_stmt = select(func.count(Offer.id)).where(Offer.company_id == company.id)
            offers_made = session.exec(offers_made_stmt).first() or 0
            
            offers_accepted_stmt = select(func.count(Offer.id)).where(
                (Offer.company_id == company.id) & (Offer.status == "accepted")
            )
            offers_accepted = session.exec(offers_accepted_stmt).first() or 0
            
            acceptance_rate = (offers_accepted / offers_made * 100) if offers_made > 0 else 0
            
            if offers_made > 0:  # Only show companies with offers
                company_metrics.append({
                    "company_name": company.name,
                    "offers_made": offers_made,
                    "offers_accepted": offers_accepted,
                    "acceptance_rate": acceptance_rate,
                })
        
        # Sort by acceptance rate descending
        company_metrics.sort(key=lambda x: x["acceptance_rate"], reverse=True)
        
        analytics_data = {
            "summary": summary,
            "by_branch": branch_stats,
            "by_company": company_metrics,
        }
        
        return render(
            request,
            "admin_analytics.html",
            current_user=user,
            role_home=home_for(user),
            analytics=analytics_data,
        )
