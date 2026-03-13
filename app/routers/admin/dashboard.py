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
        - active_jobs: Number of active job postings from verified companies
        - total_companies: Total number of verified companies
        - offers_made: Total number of offers made
        - offers_accepted: Number of accepted offers
    """
    total_students = crud.count_students(session)
    placed_students = crud.count_placed_students(session)
    active_jobs = crud.count_active_jobs(session)
    total_companies = crud.count_companies(session, verified=True)
    offers_made = crud.count_offers_made(session)
    offers_accepted = crud.count_offers_accepted(session)

    return AdminDashboardResponse(
        total_students=total_students,
        placed_students=placed_students,
        active_jobs=active_jobs,
        total_companies=total_companies,
        offers_made=offers_made,
        offers_accepted=offers_accepted
    )

