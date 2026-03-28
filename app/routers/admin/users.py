"""
Admin router for user management - specifically for admin verification.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ...database import get_session
from ... import crud
from ...auth import get_verified_admin
from ...audit import log_audit
from ...models import User
from ...enums import Role
from ...schemas import PaginationParams, UserAdminOut, UserAdminListOut

router = APIRouter(
    prefix="/users",
    tags=["admin-users"],
    dependencies=[Depends(get_verified_admin)],
)


@router.get("/", response_model=UserAdminListOut)
def admin_list_users(
    pagination: PaginationParams = Depends(),
    admin_user: User = Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    """List all users with pagination (requires verified admin)."""
    items = crud.get_all_users(session, skip=pagination.skip, limit=pagination.limit)
    total = crud.count_users(session)
    
    # Log sensitive read
    log_audit("admin.users.listed", admin_id=admin_user.id, count=len(items), total=total)

    return {
        "items": items,
        "skip": pagination.skip,
        "limit": pagination.limit,
        "total": total,
        "has_more": pagination.skip + len(items) < total,
    }


@router.get("/pending-admins", response_model=UserAdminListOut)
def list_pending_admins(
    pagination: PaginationParams = Depends(),
    current_user=Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    """
    List all pending admin requests (requires verified admin).
    Only first admin can see this - they are the ones who can approve.
    """
    # Only first admin can see pending admins
    if not current_user.is_first_admin:
        raise HTTPException(
            status_code=403,
            detail="Only the first admin can view pending admin requests"
        )
    
    items = crud.get_pending_admins(session, skip=pagination.skip, limit=pagination.limit)
    total = crud.count_pending_admins(session)

    return {
        "items": items,
        "skip": pagination.skip,
        "limit": pagination.limit,
        "total": total,
        "has_more": pagination.skip + len(items) < total,
    }


@router.post("/{user_id}/verify-admin", response_model=UserAdminOut)
def verify_admin_user(
    user_id: int,
    current_user=Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    """
    Verify an admin user.
    Only the first admin can verify other admins.
    """
    # Check if current user is first admin
    if not current_user.is_first_admin:
        raise HTTPException(
            status_code=403,
            detail="Only the first admin can verify other admins"
        )
    
    # Get the user to verify
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check if user is an admin
    if user.role != Role.admin:
        raise HTTPException(status_code=400, detail="User is not an admin")
    
    # Check if user is already verified
    if user.is_first_admin:
        raise HTTPException(status_code=400, detail="User is already the first admin")
    
    if user.verified:
        raise HTTPException(status_code=400, detail="Admin is already verified")
    
    # Verify the admin
    verified = crud.verify_admin(session, user_id, current_user.id)
    
    if not verified:
        raise HTTPException(status_code=400, detail="Could not verify admin")
    
    return verified


@router.get("/{user_id}", response_model=UserAdminOut)
def get_user(
    user_id: int,
    session: Session = Depends(get_session),
):
    """Get user by ID (requires verified admin)."""
    user = crud.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

