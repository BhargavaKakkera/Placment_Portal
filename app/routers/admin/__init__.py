from fastapi import APIRouter

router = APIRouter(prefix="/admin")

from . import companies, students, jobs, applications, users, dashboard, offers, analytics

router.include_router(companies.router)
router.include_router(students.router)
router.include_router(jobs.router)
router.include_router(applications.router)
router.include_router(offers.router)
router.include_router(users.router)
router.include_router(dashboard.router)
router.include_router(analytics.router)

__all__ = ["router"]

