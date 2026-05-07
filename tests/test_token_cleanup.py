import os
import unittest
from datetime import datetime, timedelta, timezone

# Set environment variables BEFORE importing app
os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:2005@localhost:5432/test_placement_portal",
)
os.environ["TEST_DATABASE_URL"] = "postgresql+psycopg://postgres:2005@localhost:5432/test_placement_portal"
os.environ["DEBUG"] = "true"
os.environ["LOG_LEVEL"] = "ERROR"
os.environ["SECRET_KEY"] = "588b4257178a991143c21aa7e42c102999c2c2d32e5069d6cc8389c2b3fc0fb5"
os.environ["JWT_SECRET_KEY"] = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2"
os.environ["SESSION_SECRET_KEY"] = "z9y8x7w6v5u4t3s2r1q0p9o8n7m6l5k4j3i2h1g0f9e8d7c6b5a4z3y2x1w0v9"

from sqlmodel import Session, select
from alembic import command
from alembic.config import Config

from app.database import engine
from app.models import User, TokenBlacklist
from app.crud import token_crud, user_crud
from app.datetime_utils import utc_now
from app.enums import Role


class TokenCleanupTests(unittest.TestCase):
    """Test token blacklist cleanup functionality."""

    def setUp(self):
        """Setup test database."""
        engine.dispose()
        alembic_cfg = Config("alembic.ini")
        command.downgrade(alembic_cfg, "base")
        command.upgrade(alembic_cfg, "head")
        self.session = Session(engine)

    def tearDown(self):
        """Cleanup test database."""
        self.session.close()
        engine.dispose()

    def test_cleanup_expired_tokens_removes_old_entries(self):
        """Test that cleanup_expired_tokens removes entries older than 2 days."""
        # Create test user
        user = user_crud.create_user(
            self.session, "test@example.com", "password123", Role.student
        )

        # Create old blacklist entry (3 days ago)
        old_entry = TokenBlacklist(
            token_hash="old_token_hash_1",
            user_id=user.id,
            token_purpose="password_reset",
            consumed_at=utc_now() - timedelta(days=3),
        )
        self.session.add(old_entry)

        # Create recent blacklist entry (1 day ago)
        recent_entry = TokenBlacklist(
            token_hash="recent_token_hash_1",
            user_id=user.id,
            token_purpose="email_verification",
            consumed_at=utc_now() - timedelta(days=1),
        )
        self.session.add(recent_entry)

        self.session.commit()

        # Verify both entries exist
        all_entries = self.session.exec(select(TokenBlacklist)).all()
        self.assertEqual(len(all_entries), 2)

        # Run cleanup with 2-day threshold
        deleted_count = token_crud.cleanup_expired_tokens(
            self.session, older_than_days=2
        )

        # Verify old entry was deleted
        self.assertEqual(deleted_count, 1)
        remaining_entries = self.session.exec(select(TokenBlacklist)).all()
        self.assertEqual(len(remaining_entries), 1)
        self.assertEqual(remaining_entries[0].token_hash, "recent_token_hash_1")

    def test_cleanup_expired_tokens_with_multiple_users(self):
        """Test cleanup works correctly with multiple users."""
        # Create two test users
        user1 = user_crud.create_user(
            self.session, "user1@example.com", "password123", Role.student
        )
        user2 = user_crud.create_user(
            self.session, "user2@example.com", "password123", Role.student
        )

        # Create old entries for both users
        old_entry1 = TokenBlacklist(
            token_hash="old_token_hash_user1",
            user_id=user1.id,
            token_purpose="password_reset",
            consumed_at=utc_now() - timedelta(days=5),
        )
        old_entry2 = TokenBlacklist(
            token_hash="old_token_hash_user2",
            user_id=user2.id,
            token_purpose="email_verification",
            consumed_at=utc_now() - timedelta(days=4),
        )

        # Create recent entries for both users
        recent_entry1 = TokenBlacklist(
            token_hash="recent_token_hash_user1",
            user_id=user1.id,
            token_purpose="password_reset",
            consumed_at=utc_now() - timedelta(hours=12),
        )
        recent_entry2 = TokenBlacklist(
            token_hash="recent_token_hash_user2",
            user_id=user2.id,
            token_purpose="email_verification",
            consumed_at=utc_now() - timedelta(hours=6),
        )

        self.session.add_all([old_entry1, old_entry2, recent_entry1, recent_entry2])
        self.session.commit()

        # Run cleanup
        deleted_count = token_crud.cleanup_expired_tokens(
            self.session, older_than_days=2
        )

        # Verify 2 old entries were deleted
        self.assertEqual(deleted_count, 2)
        remaining = self.session.exec(select(TokenBlacklist)).all()
        self.assertEqual(len(remaining), 2)

        # Verify remaining entries are recent ones
        remaining_hashes = {e.token_hash for e in remaining}
        self.assertIn("recent_token_hash_user1", remaining_hashes)
        self.assertIn("recent_token_hash_user2", remaining_hashes)

    def test_cleanup_with_no_expired_tokens(self):
        """Test cleanup when no tokens are expired."""
        user = user_crud.create_user(
            self.session, "test@example.com", "password123", Role.student
        )

        # Create only recent entries
        recent_entry = TokenBlacklist(
            token_hash="recent_token_hash",
            user_id=user.id,
            token_purpose="password_reset",
            consumed_at=utc_now() - timedelta(hours=12),
        )
        self.session.add(recent_entry)
        self.session.commit()

        # Run cleanup
        deleted_count = token_crud.cleanup_expired_tokens(
            self.session, older_than_days=2
        )

        # Verify nothing was deleted
        self.assertEqual(deleted_count, 0)
        remaining = self.session.exec(select(TokenBlacklist)).all()
        self.assertEqual(len(remaining), 1)

    def test_cleanup_with_empty_blacklist(self):
        """Test cleanup when blacklist is empty."""
        deleted_count = token_crud.cleanup_expired_tokens(
            self.session, older_than_days=2
        )

        # Verify cleanup completed successfully with 0 deletions
        self.assertEqual(deleted_count, 0)


if __name__ == "__main__":
    unittest.main()
