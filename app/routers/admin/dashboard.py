"""
Admin router for dashboard statistics.
"""

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ...database import get_session
from ... import crud
from ...auth import get_verified_admin
from ...schemas import AdminDashboardResponse

router = APIRouter(
    prefix="/dashboard",
    tags=["admin-dashboard"],
    dependencies=[Depends(get_verified_admin)],
)


@router.get("/", response_model=AdminDashboardResponse)
def get_dashboard_stats(
    session: Session = Depends(get_session),
):
    """
    Get dashboard statistics (requires verified admin).
    
    Returns:
        AdminDashboardResponse with the following stats:
        - total_students: Total number of students
        - placed_students: Number of students with accepted offers
        - placement_rate: Placement rate percentage
        - branch_stats: Placement breakdown per branch
        - active_jobs: Number of active job postings from verified companies
        - total_jobs: Total number of jobs created
        - total_companies: Total number of verified companies
        - pending_companies: Companies waiting for admin verification
        - pending_admins: Admin accounts waiting for first-admin approval
        - offers_made: Total number of offers made
        - offers_pending_response: Offers still awaiting student response
        - offers_accepted: Number of accepted offers
    """
    total_students = crud.count_students(session)
    placed_students = crud.count_placed_students(session)
    placement_rate = round((placed_students / total_students) * 100, 2) if total_students else 0.0
    branch_stats = crud.get_branch_placement_stats(session)
    active_jobs = crud.count_active_jobs(session)
    total_jobs = crud.count_jobs(session)
    total_companies = crud.count_companies(session, verified=True)
    pending_companies = crud.count_companies(session, verified=False)
    pending_admins = crud.count_pending_admins(session)
    offers_made = crud.count_offers_made(session)
    offers_pending_response = crud.count_offers_pending_response(session)
    offers_accepted = crud.count_offers_accepted(session)

    return AdminDashboardResponse(
        total_students=total_students,
        placed_students=placed_students,
        placement_rate=placement_rate,
        branch_stats=branch_stats,
        active_jobs=active_jobs,
        total_jobs=total_jobs,
        total_companies=total_companies,
        pending_companies=pending_companies,
        pending_admins=pending_admins,
        offers_made=offers_made,
        offers_pending_response=offers_pending_response,
        offers_accepted=offers_accepted
    )

