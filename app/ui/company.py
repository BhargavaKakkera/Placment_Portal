from fastapi import APIRouter, Request
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from .. import crud
from ..database import engine
from ..enums import CompanyApplicationAction, Role, RoleType
from ..models import Application, Job
from ..schemas import CompanyCreate, CompanyApplicationStatusUpdate, JobCreate, JobDeadlineUpdate
from ..datetime_utils import utc_now
from .helpers import branches, build_pager, dt, extract_field_errors, flt, home_for, int_or_none, parse_page_limit, read_form_with_csrf, redirect_path, redirect_to, render, require_company_profile, require_user, txt, validation_message

router = APIRouter(prefix="/company")


@router.get("", name="ui_company_dashboard")
def company_dashboard(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.company)
        if redirect:
            return redirect
        company, redirect = require_company_profile(request, session, user)
        if redirect:
            return redirect
        jobs = crud.list_company_jobs(session, company.id, 0, 5)
        offers = crud.list_company_accepted_offer_summaries(session, company.id, 0, 5)
        return render(request, "company_dashboard.html", current_user=user, role_home=home_for(user), company=company, jobs=jobs, offers=offers)


@router.get("/profile", name="ui_company_profile")
def company_profile_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.company)
        if redirect:
            return redirect
        return render(request, "company_profile.html", current_user=user, role_home=home_for(user), company=crud.get_company_by_user_id(session, user.id))


@router.post("/profile", name="ui_company_profile_post")
async def company_profile_submit(request: Request):
    try:
        form = await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_company_profile", str(exc), "warning")
    try:
        payload = CompanyCreate.model_validate({"name": str(form.get("name", "")).strip()})
    except ValidationError as exc:
        return redirect_to(request, "ui_company_profile", validation_message(exc), "warning")
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.company)
        if redirect:
            return redirect
        if crud.get_company_by_user_id(session, user.id):
            return redirect_to(request, "ui_company_profile", "Company profile already exists.", "warning")
        try:
            crud.create_company(session, user.id, payload.name)
        except IntegrityError:
            session.rollback()
            return redirect_to(request, "ui_company_profile", "Could not create company profile.", "danger")
    return redirect_to(request, "ui_company_profile", "Company profile created.", "success")


@router.get("/jobs", name="ui_company_jobs")
def company_jobs_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.company)
        if redirect:
            return redirect
        company, redirect = require_company_profile(request, session, user)
        if redirect:
            return redirect
        page, limit, skip = parse_page_limit(request, default_limit=20, max_limit=100)
        jobs = crud.list_company_jobs(session, company.id, skip, limit)
        total = crud.count_company_jobs(session, company.id)
        pager = build_pager(request, total=total, page=page, limit=limit)
        return render(
            request,
            "company_jobs.html",
            current_user=user,
            role_home=home_for(user),
            company=company,
            jobs=jobs,
            form_data={},
            field_errors={},
            error_message=None,
            pager=pager,
        )


@router.post("/jobs", name="ui_company_jobs_post")
async def company_jobs_submit(request: Request):
    try:
        form = await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_company_jobs", str(exc), "warning")
    
    # Prepare form data for potential re-rendering
    form_data = {
        "title": str(form.get("title", "")).strip(),
        "description": txt(form.get("description")) or "",
        "min_cgpa": form.get("min_cgpa", ""),
        "max_backlogs": form.get("max_backlogs", ""),
        "role_type": str(form.get("role_type", RoleType.full_time.value)),
        "internship_duration": txt(form.get("internship_duration")) or "",
        "stipend": form.get("stipend", ""),
        "ctc": form.get("ctc", ""),
        "ppo_available": str(form.get("ppo_available", "")) == "on",
        "application_deadline": form.get("application_deadline", ""),
        "allowed_branches": list(form.getlist("allowed_branches")),
    }
    
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.company)
        if redirect:
            return redirect
        company, redirect = require_company_profile(request, session, user)
        if redirect:
            return redirect

        # Required-field checks (UI-friendly errors instead of falling through to 500)
        field_errors = {}
        role_type_value = form_data["role_type"]
        selected_branches = [b for b in form_data["allowed_branches"] if b and b != "__all__"]

        if not form_data["title"]:
            field_errors["title"] = "This field is required."
        if not role_type_value:
            field_errors["role_type"] = "This field is required."
        if "__all__" not in form_data["allowed_branches"] and not selected_branches:
            field_errors["allowed_branches"] = "Select at least one branch or choose All branches."
        if role_type_value == RoleType.full_time.value and txt(form_data["ctc"]) is None:
            field_errors["ctc"] = "This field is required for full-time role."
        if role_type_value == RoleType.internship.value and txt(form_data["stipend"]) is None:
            field_errors["stipend"] = "This field is required for internship role."
        if role_type_value == RoleType.internship.value and txt(form_data["internship_duration"]) is None:
            field_errors["internship_duration"] = "This field is required for internship role."

        if field_errors:
            jobs = crud.list_company_jobs(session, company.id, 0, 50)
            return render(
                request,
                "company_jobs.html",
                current_user=user,
                role_home=home_for(user),
                company=company,
                jobs=jobs,
                form_data=form_data,
                field_errors=field_errors,
                error_message="Please fill all required fields.",
            )

        try:
            payload = JobCreate.model_validate(
                {
                    "title": form_data["title"],
                    "description": form_data["description"] or None,
                    "min_cgpa": flt(form_data["min_cgpa"]),
                    "allowed_branches": (
                        None
                        if "__all__" in form_data["allowed_branches"]
                        else branches(form_data["allowed_branches"]) or []
                    ),
                    "max_backlogs": int_or_none(form_data["max_backlogs"]),
                    "role_type": form_data["role_type"],
                    "internship_duration": form_data["internship_duration"] or None,
                    "stipend": flt(form_data["stipend"]),
                    "ctc": flt(form_data["ctc"]),
                    "ppo_available": form_data["ppo_available"],
                    "application_deadline": dt(form_data["application_deadline"]),
                }
            )
        except (ValidationError, ValueError) as exc:
            # Re-render the form with errors and data instead of redirecting
            jobs = crud.list_company_jobs(session, company.id, 0, 50)
            field_errors = extract_field_errors(exc)
            return render(
                request,
                "company_jobs.html",
                current_user=user,
                role_home=home_for(user),
                company=company,
                jobs=jobs,
                form_data=form_data,
                field_errors=field_errors,
                error_message=validation_message(exc),
            )
        try:
            crud.create_job(
                session,
                company.id,
                **payload.model_dump(mode="json")
            )
        except (ValueError, IntegrityError) as exc:
            # Re-render with error message on database error
            jobs = crud.list_company_jobs(session, company.id, 0, 50)
            return render(
                request,
                "company_jobs.html",
                current_user=user,
                role_home=home_for(user),
                company=company,
                jobs=jobs,
                form_data=form_data,
                field_errors={},
                error_message=str(exc),
            )
        except Exception:
            jobs = crud.list_company_jobs(session, company.id, 0, 50)
            return render(
                request,
                "company_jobs.html",
                current_user=user,
                role_home=home_for(user),
                company=company,
                jobs=jobs,
                form_data=form_data,
                field_errors={},
                error_message="Could not create job. Please check required fields and try again.",
            )
    return redirect_to(request, "ui_company_jobs", "Job created.", "success")


@router.post("/jobs/{job_id}/delete", name="ui_company_job_delete")
async def company_job_delete_submit(job_id: int, request: Request):
    try:
        await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_company_jobs", str(exc), "warning")
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.company)
        if redirect:
            return redirect
        company, redirect = require_company_profile(request, session, user)
        if redirect:
            return redirect
        job = session.get(Job, job_id)
        if not company or not job or job.company_id != company.id:
            return redirect_to(request, "ui_company_jobs", "Job not found.", "warning")
        try:
            ok = crud.delete_job(session, job_id)
        except ValueError as exc:
            return redirect_to(request, "ui_company_jobs", str(exc), "warning")
        if not ok:
            return redirect_to(request, "ui_company_jobs", "Could not delete job.", "danger")
    return redirect_to(request, "ui_company_jobs", "Job deleted.", "info")


@router.post("/jobs/{job_id}/deadline", name="ui_company_job_deadline_update")
async def company_job_deadline_update_submit(job_id: int, request: Request):
    try:
        form = await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_company_jobs", str(exc), "warning")
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.company)
        if redirect:
            return redirect
        company, redirect = require_company_profile(request, session, user)
        if redirect:
            return redirect
        job = session.get(Job, job_id)
        if not company or not job or job.company_id != company.id:
            return redirect_to(request, "ui_company_jobs", "Job not found.", "warning")
        try:
            # Prefer UTC-converted deadline if available, fallback to local datetime
            deadline_utc_value = form.get("application_deadline_utc")
            deadline_value = dt(deadline_utc_value) if deadline_utc_value else dt(form.get("application_deadline"))
            payload = JobDeadlineUpdate.model_validate(
                {
                    "application_deadline": deadline_value,
                }
            )
            job.application_deadline = payload.application_deadline
            job.updated_at = utc_now()
            session.add(job)
            session.commit()
            session.refresh(job)
            new_deadline = job.application_deadline.strftime("%B %d, %Y at %H:%M") if job.application_deadline else "No deadline"
        except ValidationError as exc:
            return redirect_path(request, f"/ui/company/jobs/{job_id}/applicants", validation_message(exc), "warning")
        except ValueError as exc:
            return redirect_path(request, f"/ui/company/jobs/{job_id}/applicants", str(exc), "warning")
    return redirect_to(request, "ui_company_jobs", f"Application deadline updated to: {new_deadline}", "success")


@router.post("/jobs/{job_id}/close", name="ui_company_job_close")
async def company_job_close_submit(job_id: int, request: Request):
    try:
        await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_company_jobs", str(exc), "warning")
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.company)
        if redirect:
            return redirect
        company, redirect = require_company_profile(request, session, user)
        if redirect:
            return redirect
        job = session.get(Job, job_id)
        if not company or not job or job.company_id != company.id:
            return redirect_to(request, "ui_company_jobs", "Job not found.", "warning")
        if job.closed:
            return redirect_to(request, "ui_company_jobs", "Job is already closed.", "info")
        try:
            ok = crud.close_job(session, job_id)
        except ValueError as exc:
            return redirect_to(request, "ui_company_jobs", str(exc), "warning")
        if not ok:
            return redirect_to(request, "ui_company_jobs", "Could not close job.", "danger")
    return redirect_to(request, "ui_company_jobs", "Job closed. All applications have been marked as closed.", "success")


@router.get("/jobs/{job_id}/applicants", name="ui_company_applicants")
def company_applicants_page(job_id: int, request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.company)
        if redirect:
            return redirect
        company, redirect = require_company_profile(request, session, user)
        if redirect:
            return redirect
        job = session.get(Job, job_id)
        if not company or not job or job.company_id != company.id:
            return redirect_to(request, "ui_company_jobs", "Not allowed to view applicants for that job.", "warning")
        page, limit, skip = parse_page_limit(request, default_limit=20, max_limit=100)
        applicants = crud.list_company_applicant_summaries(session, job_id, skip, limit)
        total = crud.count_applicants_for_job(session, job_id)
        pager = build_pager(request, total=total, page=page, limit=limit)
        return render(
            request,
            "company_applicants.html",
            current_user=user,
            role_home=home_for(user),
            job=job,
            applicants=applicants,
            pager=pager,
        )


@router.post("/applications/{application_id}", name="ui_company_application_action")
async def company_application_action_submit(application_id: int, request: Request):
    try:
        form = await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_company_jobs", str(exc), "warning")
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.company)
        if redirect:
            return redirect
        company, redirect = require_company_profile(request, session, user)
        if redirect:
            return redirect
        application = session.get(Application, application_id)
        if not company or not application:
            return redirect_to(request, "ui_company_jobs", "Application not found.", "warning")
        job = session.get(Job, application.job_id)
        if not job or job.company_id != company.id:
            return redirect_to(request, "ui_company_jobs", "Not allowed to modify this application.", "danger")
        redirect_url = f"/ui/company/jobs/{job.id}/applicants"
        if job.closed:
            return redirect_path(request, redirect_url, "Cannot modify applications for a closed job.", "warning")
        try:
            status_value = str(form.get("status", CompanyApplicationAction.shortlisted.value)).strip()
            ctc_value = flt(form.get("ctc"))
            # Prefer UTC-converted deadline if available, fallback to local datetime
            deadline_utc_value = form.get("offer_response_deadline_utc")
            deadline_value = dt(deadline_utc_value) if deadline_utc_value else dt(form.get("offer_response_deadline"))
            payload = CompanyApplicationStatusUpdate.model_validate(
                {
                    "status": status_value,
                    "ctc": ctc_value,
                    "offer_response_deadline": deadline_value,
                }
            )
        except (ValidationError, ValueError) as exc:
            return redirect_path(request, redirect_url, validation_message(exc), "warning")
        try:
            crud.apply_company_action(
                session,
                application,
                job,
                company.id,
                payload.status,
                payload.ctc,
                payload.offer_response_deadline,
            )
        except ValueError as exc:
            session.rollback()
            return redirect_path(request, redirect_url, str(exc), "warning")
        except Exception as exc:
            session.rollback()
            return redirect_path(request, redirect_url, f"An unexpected error occurred: {str(exc)}", "danger")
    return redirect_path(request, redirect_url, "Application updated successfully.", "success")


@router.get("/offers", name="ui_company_offers")
def company_offers_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.company)
        if redirect:
            return redirect
        company, redirect = require_company_profile(request, session, user)
        if redirect:
            return redirect
        page, limit, skip = parse_page_limit(request, default_limit=20, max_limit=100)
        offers = crud.list_company_accepted_offer_summaries(session, company.id, skip, limit)
        total = crud.count_company_accepted_offers(session, company.id)
        pager = build_pager(request, total=total, page=page, limit=limit)
        return render(
            request,
            "company_offers.html",
            current_user=user,
            role_home=home_for(user),
            offers=offers,
            pager=pager,
        )
