"""
Admin router for user management - specifically for admin verification.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ...database import get_session
from ... import crud
from ...auth import get_verified_admin
from ...models import User
from ...enums import Role

router = APIRouter(prefix="/users", tags=["admin-users"])


@router.get("/")
def admin_list_users(
    skip: int = Query(0, ge=0, description="Pagination skip"),
    limit: int = Query(100, ge=1, le=100, description="Pagination limit"),
    current_user=Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    """List all users with pagination (requires verified admin)."""
    items = crud.get_all_users(session, skip=skip, limit=limit)
    total = crud.count_users(session)

    return {
        "items": items,
        "skip": skip,
        "limit": limit,
        "total": total
    }


@router.get("/pending-admins")
def list_pending_admins(
    skip: int = Query(0, ge=0, description="Pagination skip"),
    limit: int = Query(100, ge=1, le=100, description="Pagination limit"),
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
    
    items = crud.get_pending_admins(session, skip=skip, limit=limit)
    total = crud.count_pending_admins(session)

    return {
        "items": items,
        "skip": skip,
        "limit": limit,
        "total": total
    }


@router.post("/{user_id}/verify-admin")
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


@router.get("/{user_id}")
def get_user(
    user_id: int,
    current_user=Depends(get_verified_admin),
    session: Session = Depends(get_session),
):
    """Get user by ID (requires verified admin)."""
    user = crud.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

