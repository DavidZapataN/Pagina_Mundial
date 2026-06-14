"""
FastAPI dependencies for authentication and session management.

Provides:
  get_current_user_or_none — reads session_token cookie; returns User or None
  require_current_user     — raises UnauthenticatedError if no valid session

Usage in a route::

    @router.get("/protected")
    def protected_view(user: User = Depends(require_current_user)):
        ...

    @router.get("/optional-auth")
    def public_view(user: User | None = Depends(get_current_user_or_none)):
        ...

Requirements: 1.3, 1.5, 1.6
"""

from __future__ import annotations

from fastapi import Depends, Request
from sqlmodel import Session

from app.database import get_session
from app.exceptions import UnauthenticatedError
from app.models import User
from app.modules.auth.service import AuthService


def get_current_user_or_none(
    request: Request,
    session: Session = Depends(get_session),
) -> User | None:
    """
    Read the ``session_token`` cookie and return the authenticated User, or
    ``None`` if the cookie is absent, expired, or carries an invalid signature.

    The session's sliding window is renewed on each successful resolution
    (delegated to ``AuthService.get_current_user``).

    Requirements: 1.6
    """
    token = request.cookies.get("session_token")
    if not token:
        return None

    svc = AuthService(session)
    return svc.get_current_user(token)


def require_current_user(
    user: User | None = Depends(get_current_user_or_none),
) -> User:
    """
    Return the authenticated User, or raise ``UnauthenticatedError`` if none.

    Routers that require a valid session should declare this as a dependency::

        @router.post("/predictions/{match_id}")
        def save_prediction(user: User = Depends(require_current_user), ...):
            ...

    The ``UnauthenticatedError`` is expected to be caught by a global
    exception handler in main.py and converted to an appropriate HTTP
    redirect or 401 response.

    Requirements: 1.3, 1.5
    """
    if user is None:
        raise UnauthenticatedError("Se requiere iniciar sesión para acceder a esta página")
    return user
