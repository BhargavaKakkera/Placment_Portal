from fastapi import APIRouter

from .admin import router as admin_router
from .company import router as company_router
from .public import router as public_router
from .student import router as student_router

router = APIRouter(prefix="/ui", tags=["ui"])
router.include_router(public_router)
router.include_router(student_router)
router.include_router(company_router)
router.include_router(admin_router)

__all__ = ["router"]
