"""
Token blacklist CRUD operations for tracking used tokens.
"""

import hashlib
from sqlmodel import Session, select
from typing import Optional
from ..models import TokenBlacklist
from ..logger import get_logger

logger = get_logger(__name__)


def _hash_token(token: str) -> str:
    """Hash a token using SHA256."""
    return hashlib.sha256(token.encode()).hexdigest()


def mark_token_as_used(
    session: Session,
    token: str,
    user_id: int,
    token_purpose: str,
) -> bool:
    """
    Mark a token as used/consumed.
    
    Args:
        session: Database session
        token: The token string to mark as used
        user_id: User ID associated with token
        token_purpose: Purpose of token ('password_reset' or 'email_verification')
    
    Returns:
        True if marked successfully, False if token already used
    """
    token_hash = _hash_token(token)
    
    # Check if token already used
    existing = session.exec(
        select(TokenBlacklist).where(TokenBlacklist.token_hash == token_hash)
    ).first()
    
    if existing:
        logger.warning(f"Attempted reuse of consumed {token_purpose} token for user {user_id}")
        return False
    
    # Add token to blacklist
    blacklist_entry = TokenBlacklist(
        token_hash=token_hash,
        user_id=user_id,
        token_purpose=token_purpose,
    )
    session.add(blacklist_entry)
    try:
        session.commit()
        logger.debug(f"Marked {token_purpose} token as consumed for user {user_id}")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to mark token as used: {str(e)}", exc_info=True)
        return False


def is_token_used(session: Session, token: str) -> bool:
    """
    Check if a token has already been used/consumed.
    
    Args:
        session: Database session
        token: The token string to check
    
    Returns:
        True if token is in blacklist (used), False if not in blacklist (unused)
    """
    token_hash = _hash_token(token)
    entry = session.exec(
        select(TokenBlacklist).where(TokenBlacklist.token_hash == token_hash)
    ).first()
    return entry is not None


def invalidate_user_tokens(session: Session, user_id: int) -> int:
    """
    Invalidate all tokens for a user (useful on password change for security).
    
    Args:
        session: Database session
        user_id: User ID
    
    Returns:
        Number of tokens invalidated
    """
    try:
        entries = session.exec(
            select(TokenBlacklist).where(TokenBlacklist.user_id == user_id)
        ).all()
        count = len(entries)
        
        for entry in entries:
            session.delete(entry)
        
        session.commit()
        logger.info(f"Invalidated {count} tokens for user {user_id}")
        return count
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to invalidate user tokens: {str(e)}", exc_info=True)
        return 0
