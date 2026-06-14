"""
Unit tests for the authentication service.

Covers login, logout, session expiry, and the 24-hour sliding session window.

Requirements: 1.3, 1.5, 1.6
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlmodel import select

from app.exceptions import InvalidCredentialsError
from app.models import Session as DBSession


# ---------------------------------------------------------------------------
# 1. Login with correct credentials returns a token
# ---------------------------------------------------------------------------

def test_login_with_correct_credentials_returns_token(auth_service):
    """
    Registering a user and logging in with the correct password
    should return a non-empty string token.

    Requirements: 1.3
    """
    auth_service.register("alice", "correct_password")
    token = auth_service.login("alice", "correct_password")

    assert isinstance(token, str)
    assert len(token) > 0


# ---------------------------------------------------------------------------
# 2. Login with wrong password raises InvalidCredentialsError
# ---------------------------------------------------------------------------

def test_login_with_wrong_password_raises(auth_service):
    """
    Logging in with an incorrect password should raise InvalidCredentialsError.

    Requirements: 1.3
    """
    auth_service.register("bob", "right_password")

    with pytest.raises(InvalidCredentialsError):
        auth_service.login("bob", "wrong_password")


# ---------------------------------------------------------------------------
# 3. Expired session returns None from get_current_user
# ---------------------------------------------------------------------------

def test_expired_session_returns_none(auth_service):
    """
    After a session's expires_at is set to the past, get_current_user()
    should return None.

    Requirements: 1.6
    """
    auth_service.register("carol", "pass123")
    token = auth_service.login("carol", "pass123")

    # Manually expire the session by setting expires_at to the past
    db_session = auth_service._session.exec(
        select(DBSession).where(DBSession.token == token)
    ).first()
    assert db_session is not None

    db_session.expires_at = datetime.utcnow() - timedelta(hours=1)
    auth_service._session.add(db_session)
    auth_service._session.commit()

    result = auth_service.get_current_user(token)
    assert result is None


# ---------------------------------------------------------------------------
# 4. Logout invalidates the token
# ---------------------------------------------------------------------------

def test_logout_invalidates_token(auth_service):
    """
    After logout, validate_session() for that token should return False.

    Requirements: 1.5
    """
    auth_service.register("dave", "s3cr3t")
    token = auth_service.login("dave", "s3cr3t")

    # Confirm session is valid before logout
    assert auth_service.validate_session(token) is True

    auth_service.logout(token)

    assert auth_service.validate_session(token) is False


# ---------------------------------------------------------------------------
# 5. Sliding session window renews expires_at on access
# ---------------------------------------------------------------------------

def test_sliding_session_renews_timestamp(auth_service):
    """
    Calling get_current_user() on a valid session should push expires_at
    forward, implementing the 24-hour sliding window.

    Requirements: 1.6
    """
    auth_service.register("eve", "hunter2")
    token = auth_service.login("eve", "hunter2")

    # Record the original expires_at
    original_session = auth_service._session.exec(
        select(DBSession).where(DBSession.token == token)
    ).first()
    assert original_session is not None
    original_expires_at = original_session.expires_at

    # Call get_current_user — this should renew the sliding window
    user = auth_service.get_current_user(token)
    assert user is not None
    assert user.username == "eve"

    # Fetch the session row again to see the updated timestamp
    auth_service._session.expire_all()
    renewed_session = auth_service._session.exec(
        select(DBSession).where(DBSession.token == token)
    ).first()
    assert renewed_session is not None

    assert renewed_session.expires_at > original_expires_at, (
        f"Expected expires_at to be renewed (sliding window), but "
        f"original={original_expires_at}, renewed={renewed_session.expires_at}"
    )
