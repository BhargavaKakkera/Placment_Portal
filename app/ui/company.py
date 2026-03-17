from fastapi import APIRouter, Request
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from .. import crud
from ..database import engine
from ..enums import CompanyApplicationAction, Role, RoleType
from ..models import Application, Job
from ..schemas import CompanyCreate, CompanyApplicationStatusUpdate, JobCreate
from .helpers import branches, dt, flt, home_for, int_or_none, redirect_path, redirect_to, render, require_company_profile, require_user, txt, validation_message

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
    form = await request.form()
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


@router.post("/delete", name="ui_company_delete")
def company_delete_submit(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.company)
        if redirect:
            return redirect
        company, redirect = require_company_profile(request, session, user)
        if redirect:
            return redirect
        if not crud.delete_company(session, company.id):
            return redirect_to(request, "ui_company_profile", "Could not deactivate company.", "danger")
    request.session.clear()
    return redirect_to(request, "ui_home", "Company deactivated.", "info")


@router.get("/jobs", name="ui_company_jobs")
def company_jobs_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.company)
        if redirect:
            return redirect
        company, redirect = require_company_profile(request, session, user)
        if redirect:
            return redirect
        jobs = crud.list_company_jobs(session, company.id, 0, 50)
        return render(request, "company_jobs.html", current_user=user, role_home=home_for(user), company=company, jobs=jobs)


@router.post("/jobs", name="ui_company_jobs_post")
async def company_jobs_submit(request: Request):
    form = await request.form()
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.company)
        if redirect:
            return redirect
        company, redirect = require_company_profile(request, session, user)
        if redirect:
            return redirect
        try:
            payload = JobCreate.model_validate(
                {
                    "title": str(form.get("title", "")).strip(),
                    "description": txt(form.get("description")),
                    "min_cgpa": flt(form.get("min_cgpa")),
                    "allowed_branches": branches(list(form.getlist("allowed_branches"))),
                    "max_backlogs": int_or_none(form.get("max_backlogs")),
                    "role_type": str(form.get("role_type", RoleType.full_time.value)),
                    "internship_duration": txt(form.get("internship_duration")),
                    "stipend": flt(form.get("stipend")),
                    "ctc": flt(form.get("ctc")),
                    "ppo_available": str(form.get("ppo_available", "")) == "on",
                    "application_deadline": dt(form.get("application_deadline")),
                }
            )
        except (ValidationError, ValueError) as exc:
            return redirect_to(request, "ui_company_jobs", validation_message(exc), "warning")
        try:
            crud.create_job(
                session,
                company.id,
                **payload.model_dump(mode="json")
            )
        except ValueError as exc:
            return redirect_to(request, "ui_company_jobs", str(exc), "warning")
    return redirect_to(request, "ui_company_jobs", "Job created.", "success")


@router.post("/jobs/{job_id}/delete", name="ui_company_job_delete")
def company_job_delete_submit(job_id: int, request: Request):
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
        return render(request, "company_applicants.html", current_user=user, role_home=home_for(user), job=job, applicants=crud.list_company_applicant_summaries(session, job_id, 0, 100))


@router.post("/applications/{application_id}", name="ui_company_application_action")
async def company_application_action_submit(application_id: int, request: Request):
    form = await request.form()
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
        try:
            payload = CompanyApplicationStatusUpdate.model_validate(
                {
                    "status": str(form.get("status", CompanyApplicationAction.shortlisted.value)),
                    "ctc": flt(form.get("ctc")),
                    "offer_response_deadline": dt(form.get("offer_response_deadline")),
                }
            )
        except (ValidationError, ValueError) as exc:
            return redirect_path(request, f"/ui/company/jobs/{job.id}/applicants", validation_message(exc), "warning")
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
            return redirect_path(request, f"/ui/company/jobs/{job.id}/applicants", str(exc), "warning")
    return redirect_path(request, f"/ui/company/jobs/{job.id}/applicants", "Application updated.", "success")


@router.get("/offers", name="ui_company_offers")
def company_offers_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.company)
        if redirect:
            return redirect
        company, redirect = require_company_profile(request, session, user)
        if redirect:
            return redirect
        offers = crud.list_company_accepted_offer_summaries(session, company.id, 0, 100)
        return render(request, "company_offers.html", current_user=user, role_home=home_for(user), offers=offers)
