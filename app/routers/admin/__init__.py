"""
Admin routers for managing the Placement Portal.

This module contains admin endpoints organized by resource:
- companies: Company verification and management
- students: Student verification and management
- jobs: Job posting management
- applications: Application management
- users: Admin user management (verification of other admins)
"""

from fastapi import APIRouter

# Create main admin router
router = APIRouter(prefix="/admin")

# Import and include sub-routers
from . import companies, students, jobs, applications, users, dashboard

router.include_router(companies.router)
router.include_router(students.router)
router.include_router(jobs.router)
router.include_router(applications.router)
router.include_router(users.router)
router.include_router(dashboard.router)

__all__ = ["router"]

