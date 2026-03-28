from fastapi import APIRouter, Request
from pydantic import ValidationError
from sqlmodel import Session

from .. import crud
from ..database import engine
from ..enums import OfferStatus, Role
from ..schemas import StudentUpdate
from .helpers import eligible_jobs, home_for, read_form_with_csrf, redirect_to, render, require_student_profile, require_user, txt, validation_message

router = APIRouter(prefix="/student")


@router.get("", name="ui_student_dashboard")
def student_dashboard(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.student)
        if redirect:
            return redirect
        student, redirect = require_student_profile(request, session, user)
        if redirect:
            return redirect
        applications = crud.list_student_application_summaries(session, student.id, 0, 5)
        offers = crud.list_student_offer_summaries(session, student.id, OfferStatus.offered)
        return render(request, "student_dashboard.html", current_user=user, role_home=home_for(user), student=student, applications=applications, offers=offers)


@router.get("/profile", name="ui_student_profile")
def student_profile_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.student)
        if redirect:
            return redirect
        student, redirect = require_student_profile(request, session, user)
        if redirect:
            return redirect
        return render(request, "student_profile.html", current_user=user, role_home=home_for(user), student=student)


@router.post("/profile", name="ui_student_profile_post")
async def student_profile_submit(request: Request):
    try:
        form = await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_student_profile", str(exc), "warning")
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.student)
        if redirect:
            return redirect
        student, redirect = require_student_profile(request, session, user)
        if redirect:
            return redirect
        try:
            payload = StudentUpdate.model_validate(
                {
                    "phone": txt(form.get("phone")),
                    "personal_email": txt(form.get("personal_email")),
                    "address": txt(form.get("address")),
                    "resume_url": txt(form.get("resume_url")),
                    "github_url": txt(form.get("github_url")),
                    "linkedin_url": txt(form.get("linkedin_url")),
                    "leetcode_url": txt(form.get("leetcode_url")),
                    "codeforces_url": txt(form.get("codeforces_url")),
                    "hackerrank_url": txt(form.get("hackerrank_url")),
                    "portfolio_url": txt(form.get("portfolio_url")),
                    "other_coding_url": txt(form.get("other_coding_url")),
                }
            )
        except ValidationError as exc:
            return redirect_to(request, "ui_student_profile", validation_message(exc), "warning")
        updated = crud.update_student(
            session,
            student.id,
            **payload.model_dump(mode="json")
        )
        if not updated:
            return redirect_to(request, "ui_student_profile", "Could not update profile.", "danger")
    return redirect_to(request, "ui_student_profile", "Profile updated.", "success")


@router.post("/delete", name="ui_student_delete")
async def student_delete_submit(request: Request):
    try:
        await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_student_profile", str(exc), "warning")
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.student)
        if redirect:
            return redirect
        student, redirect = require_student_profile(request, session, user)
        if redirect:
            return redirect
        if not crud.delete_student(session, student.id):
            return redirect_to(request, "ui_student_profile", "Could not deactivate student profile.", "danger")
    request.session.clear()
    return redirect_to(request, "ui_home", "Student profile deactivated.", "info")


@router.get("/jobs", name="ui_student_jobs")
def student_jobs_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.student)
        if redirect:
            return redirect
        student, redirect = require_student_profile(request, session, user)
        if redirect:
            return redirect
        return render(request, "student_jobs.html", current_user=user, role_home=home_for(user), student=student, jobs=eligible_jobs(session, student))


@router.post("/jobs/{job_id}/apply", name="ui_student_apply")
async def student_apply_submit(job_id: int, request: Request):
    try:
        await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_student_jobs", str(exc), "warning")
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.student)
        if redirect:
            return redirect
        student, redirect = require_student_profile(request, session, user)
        if redirect:
            return redirect
        try:
            crud.apply_job(session, student.id, job_id)
        except ValueError as exc:
            return redirect_to(request, "ui_student_jobs", str(exc), "warning")
    return redirect_to(request, "ui_student_applications", "Application submitted.", "success")


@router.get("/applications", name="ui_student_applications")
def student_applications_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.student)
        if redirect:
            return redirect
        student, redirect = require_student_profile(request, session, user)
        if redirect:
            return redirect
        items = crud.list_student_application_summaries(session, student.id, 0, 50)
        return render(request, "student_applications.html", current_user=user, role_home=home_for(user), applications=items)


@router.get("/offers", name="ui_student_offers")
def student_offers_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.student)
        if redirect:
            return redirect
        student, redirect = require_student_profile(request, session, user)
        if redirect:
            return redirect
        offered = crud.list_student_offer_summaries(session, student.id, OfferStatus.offered)
        accepted = crud.list_student_offer_summaries(session, student.id, OfferStatus.accepted)
        return render(request, "student_offers.html", current_user=user, role_home=home_for(user), offered=offered, accepted=accepted)


@router.post("/offers/{offer_id}/accept", name="ui_student_offer_accept")
async def student_accept_offer(offer_id: int, request: Request):
    try:
        await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_student_offers", str(exc), "warning")
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.student)
        if redirect:
            return redirect
        student, redirect = require_student_profile(request, session, user)
        if redirect:
            return redirect
        if not crud.accept_offer(session, offer_id, student.id):
            return redirect_to(request, "ui_student_offers", "Could not accept offer.", "warning")
    return redirect_to(request, "ui_student_offers", "Offer accepted.", "success")


@router.post("/offers/{offer_id}/decline", name="ui_student_offer_decline")
async def student_decline_offer(offer_id: int, request: Request):
    try:
        await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_student_offers", str(exc), "warning")
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.student)
        if redirect:
            return redirect
        student, redirect = require_student_profile(request, session, user)
        if redirect:
            return redirect
        if not crud.decline_offer(session, offer_id, student.id):
            return redirect_to(request, "ui_student_offers", "Could not decline offer.", "warning")
    return redirect_to(request, "ui_student_offers", "Offer declined.", "info")
