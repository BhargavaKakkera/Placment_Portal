import hashlib
from datetime import timedelta
from sqlmodel import Session, select
from typing import Optional
from ..models import TokenBlacklist
from ..logger import get_logger
from ..datetime_utils import utc_now

logger = get_logger(__name__)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def mark_token_as_used(
    session: Session,
    token: str,
    user_id: int,
    token_purpose: str,
) -> bool:
    token_hash = _hash_token(token)
    
    existing = session.exec(
        select(TokenBlacklist).where(TokenBlacklist.token_hash == token_hash)
    ).first()
    
    if existing:
        logger.warning(f"Attempted reuse of consumed {token_purpose} token for user {user_id}")
        return False
    
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
    token_hash = _hash_token(token)
    entry = session.exec(
        select(TokenBlacklist).where(TokenBlacklist.token_hash == token_hash)
    ).first()
    return entry is not None


def invalidate_user_tokens(session: Session, user_id: int) -> int:
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


def cleanup_expired_tokens(session: Session, older_than_days: int = 2) -> int:
    try:
        cutoff_time = utc_now() - timedelta(days=older_than_days)
        
        entries = session.exec(
            select(TokenBlacklist).where(TokenBlacklist.consumed_at < cutoff_time)
        ).all()
        count = len(entries)
        
        for entry in entries:
            session.delete(entry)
        
        session.commit()
        logger.info(f"Cleaned up {count} expired tokens (older than {older_than_days} days)")
        return count
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to cleanup expired tokens: {str(e)}", exc_info=True)
        return 0
