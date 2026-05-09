from fastapi import APIRouter, Request
from pydantic import ValidationError
from sqlmodel import Session, select

from .. import crud
from ..database import engine
from ..enums import OfferStatus, OfferStatusReason, ApplicationStatus, ApplicationStatusReason, Role
from ..schemas import StudentUpdate
from ..crud.state_transitions import get_active_offers
from .helpers import build_pager, eligible_jobs, extract_field_errors, home_for, parse_page_limit, read_form_with_csrf, redirect_to, render, require_student_profile, require_user, txt, validation_message

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
        return render(
            request,
            "student_profile.html",
            current_user=user,
            role_home=home_for(user),
            student=student,
            form_data={},
            field_errors={},
            error_message=None,
        )


@router.post("/profile", name="ui_student_profile_post")
async def student_profile_submit(request: Request):
    try:
        form = await read_form_with_csrf(request)
    except ValueError as exc:
        return redirect_to(request, "ui_student_profile", str(exc), "warning")
    
    # Prepare form data
    form_data = {
        "phone": txt(form.get("phone")) or "",
        "personal_email": txt(form.get("personal_email")) or "",
        "address": txt(form.get("address")) or "",
        "resume_url": txt(form.get("resume_url")) or "",
        "github_url": txt(form.get("github_url")) or "",
        "linkedin_url": txt(form.get("linkedin_url")) or "",
        "leetcode_url": txt(form.get("leetcode_url")) or "",
        "codeforces_url": txt(form.get("codeforces_url")) or "",
        "hackerrank_url": txt(form.get("hackerrank_url")) or "",
        "portfolio_url": txt(form.get("portfolio_url")) or "",
        "other_coding_url": txt(form.get("other_coding_url")) or "",
    }
    
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.student)
        if redirect:
            return redirect
        student, redirect = require_student_profile(request, session, user)
        if redirect:
            return redirect
        try:
            payload = StudentUpdate.model_validate(form_data)
        except ValidationError as exc:
            field_errors = extract_field_errors(exc)
            return render(
                request,
                "student_profile.html",
                current_user=user,
                role_home=home_for(user),
                student=student,
                form_data=form_data,
                field_errors=field_errors,
                error_message=validation_message(exc),
            )
        update_data = payload.model_dump(exclude_unset=True, mode="json")
        updated = crud.update_student(session, student.id, **update_data)
        if not updated:
            return render(
                request,
                "student_profile.html",
                current_user=user,
                role_home=home_for(user),
                student=student,
                form_data=form_data,
                field_errors={},
                error_message="Could not update profile.",
            )
    return redirect_to(request, "ui_student_profile", "Profile updated.", "success")


@router.get("/jobs", name="ui_student_jobs")
def student_jobs_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.student)
        if redirect:
            return redirect
        student, redirect = require_student_profile(request, session, user)
        if redirect:
            return redirect
        page, limit, skip = parse_page_limit(request, default_limit=20, max_limit=100)
        all_jobs = eligible_jobs(session, student)
        total = len(all_jobs)
        jobs = all_jobs[skip: skip + limit]
        companies_by_id = {company.id: company for company in crud.list_companies(session, 0, 1000, include_inactive=True)}
        pager = build_pager(request, total=total, page=page, limit=limit)
        return render(
            request,
            "student_jobs.html",
            current_user=user,
            role_home=home_for(user),
            student=student,
            jobs=jobs,
            companies_by_id=companies_by_id,
            pager=pager,
        )


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
        page, limit, skip = parse_page_limit(request, default_limit=20, max_limit=100)
        items = crud.list_student_application_summaries(session, student.id, skip, limit)
        total = crud.count_student_applications(session, student.id)
        pager = build_pager(request, total=total, page=page, limit=limit)
        return render(
            request,
            "student_applications.html",
            current_user=user,
            role_home=home_for(user),
            applications=items,
            pager=pager,
        )


@router.get("/offers", name="ui_student_offers")
def student_offers_page(request: Request):
    with Session(engine) as session:
        user, redirect = require_user(request, session, Role.student)
        if redirect:
            return redirect
        student, redirect = require_student_profile(request, session, user)
        if redirect:
            return redirect
        page, limit, skip = parse_page_limit(request, default_limit=20, max_limit=100)
        
        # Get all offers with job/company details
        offered = crud.list_student_offer_summaries(session, student.id, OfferStatus.offered, skip, limit)
        accepted = crud.list_student_offer_summaries(session, student.id, OfferStatus.accepted, skip, limit)
        
        # Get total count for pagination
        total_offered = crud.count_student_offers(session, student.id, OfferStatus.offered)
        total_accepted = crud.count_student_offers(session, student.id, OfferStatus.accepted)
        total = total_offered + total_accepted
        
        pager = build_pager(request, total=total, page=page, limit=limit)
        return render(
            request,
            "student_offers.html",
            current_user=user,
            role_home=home_for(user),
            offered=offered,
            accepted=accepted,
            pager=pager,
        )


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
