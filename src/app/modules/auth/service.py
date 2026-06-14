"""
Authentication service for Polla del Mundial.

Provides user registration, login, logout, and session management with:
- bcrypt password hashing
- itsdangerous URLSafeTimedSerializer for cryptographically signed tokens
- 24-hour sliding session window stored in the Session table

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6
"""

from __future__ import annotations

import logging
from datetime import timedelta

import bcrypt
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlmodel import Session, select

from app.config import settings
from app.exceptions import InvalidCredentialsError, UsernameAlreadyExistsError
from app.models import Session as DBSession
from app.models import User
from app.utils import utcnow

logger = logging.getLogger("polla.auth")

# ---------------------------------------------------------------------------
# Type alias for the signed session token string
# ---------------------------------------------------------------------------

SessionToken = str


class AuthService:
    """
    Domain service for all authentication and session operations.

    Accepts a SQLModel ``Session`` at construction time so callers (FastAPI
    dependencies, tests) control the DB session lifecycle and transaction
    boundaries explicitly.

    Usage::

        with Session(engine) as db_session:
            svc = AuthService(db_session)
            user = svc.register("alice", "s3cr3t")
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._serializer = URLSafeTimedSerializer(
            secret_key=settings.SECRET_KEY,
            salt="session",
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, username: str, password: str) -> User:
        """
        Register a new user with a bcrypt-hashed password.

        Raises:
            UsernameAlreadyExistsError: if *username* is already taken.

        Requirements: 1.1, 1.2
        """
        existing = self._session.exec(
            select(User).where(User.username == username)
        ).first()
        if existing is not None:
            logger.warning("Registration attempt for existing username: %s", username)
            raise UsernameAlreadyExistsError(
                f"El nombre de usuario '{username}' ya está en uso"
            )

        password_hash = bcrypt.hashpw(
            password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

        # Grant admin privileges when the username matches ADMIN_USERNAME.
        is_admin = username == settings.ADMIN_USERNAME

        user = User(
            username=username,
            password_hash=password_hash,
            is_admin=is_admin,
        )
        self._session.add(user)
        self._session.commit()
        self._session.refresh(user)
        logger.info("User registered: %s (admin=%s)", username, is_admin)
        return user

    def login(self, username: str, password: str) -> SessionToken:
        """
        Authenticate a user and return a signed session token.

        Any pre-existing session for the user is invalidated before creating
        the new one (requirement 1.3).

        Raises:
            InvalidCredentialsError: if credentials are incorrect.

        Requirements: 1.3, 1.4
        """
        user = self._session.exec(
            select(User).where(User.username == username)
        ).first()

        if user is None or not bcrypt.checkpw(
            password.encode("utf-8"), user.password_hash.encode("utf-8")
        ):
            logger.warning("Failed login attempt for username: %s", username)
            raise InvalidCredentialsError("Usuario o contraseña incorrectos")

        # Invalidate any existing session for this user (req 1.3).
        self._invalidate_existing_sessions(user.id)  # type: ignore[arg-type]

        # Build a signed token whose payload is the user's id.
        token: str = self._serializer.dumps({"user_id": user.id})

        now = utcnow()
        session = DBSession(
            user_id=user.id,  # type: ignore[arg-type]
            token=token,
            last_accessed=now,
            expires_at=now + timedelta(hours=settings.SESSION_DURATION_HOURS),
        )
        self._session.add(session)
        self._session.commit()
        logger.info("User logged in: %s", username)
        return token

    def change_password(
        self, user_id: int, current_password: str, new_password: str
    ) -> None:
        """
        Cambia la contraseña de un usuario tras verificar la actual.

        Invalida todas las sesiones existentes para forzar un nuevo login.

        Raises:
            InvalidCredentialsError: si la contraseña actual no coincide o la
                nueva no cumple la longitud mínima.
        """
        user = self._session.get(User, user_id)
        if user is None or not bcrypt.checkpw(
            current_password.encode("utf-8"), user.password_hash.encode("utf-8")
        ):
            raise InvalidCredentialsError("La contraseña actual es incorrecta")

        if len(new_password) < 4:
            raise InvalidCredentialsError("La nueva contraseña es demasiado corta")

        user.password_hash = bcrypt.hashpw(
            new_password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        self._session.add(user)
        self._invalidate_existing_sessions(user_id)
        self._session.commit()
        logger.info("Password changed for user_id=%d", user_id)

    def logout(self, session_token: str) -> None:
        """
        Delete the session identified by *session_token*.

        If the token does not exist this is a no-op (idempotent).

        Requirements: 1.5
        """
        db_session = self._session.exec(
            select(DBSession).where(DBSession.token == session_token)
        ).first()
        if db_session is not None:
            self._session.delete(db_session)
            self._session.commit()
            logger.info("Session deleted for token (truncated): %s…", session_token[:12])

    def get_current_user(self, session_token: str) -> User | None:
        """
        Return the authenticated user for *session_token*, or ``None``.

        On each successful call the session's sliding window is renewed:
        ``last_accessed`` and ``expires_at`` are updated to extend the
        session by another ``SESSION_DURATION_HOURS`` hours.

        Requirements: 1.6
        """
        db_session = self._get_valid_session(session_token)
        if db_session is None:
            return None

        # Renew the sliding window.
        now = utcnow()
        db_session.last_accessed = now
        db_session.expires_at = now + timedelta(hours=settings.SESSION_DURATION_HOURS)
        self._session.add(db_session)
        self._session.commit()

        user = self._session.get(User, db_session.user_id)
        return user

    def validate_session(self, session_token: str) -> bool:
        """
        Return ``True`` if *session_token* corresponds to a valid, unexpired
        session; ``False`` otherwise.

        Requirements: 1.6
        """
        return self._get_valid_session(session_token) is not None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_valid_session(self, session_token: str) -> DBSession | None:
        """
        Look up a session by token and check it has not expired.

        Also verifies the itsdangerous signature so forged tokens are
        rejected even if they somehow appear in the DB.

        Returns the ``DBSession`` row on success, ``None`` otherwise.
        """
        # Verify the cryptographic signature first (fast, no DB hit needed
        # for obviously invalid tokens).
        try:
            self._serializer.loads(session_token)
        except BadSignature:
            logger.debug("Invalid token signature rejected.")
            return None

        db_session = self._session.exec(
            select(DBSession).where(DBSession.token == session_token)
        ).first()

        if db_session is None:
            return None

        if utcnow() > db_session.expires_at:
            # Session has expired — clean it up.
            self._session.delete(db_session)
            self._session.commit()
            logger.info("Expired session deleted.")
            return None

        return db_session

    def _invalidate_existing_sessions(self, user_id: int) -> None:
        """Delete all active sessions for *user_id*."""
        old_sessions = self._session.exec(
            select(DBSession).where(DBSession.user_id == user_id)
        ).all()
        for s in old_sessions:
            self._session.delete(s)
        if old_sessions:
            self._session.commit()
            logger.debug(
                "Invalidated %d existing session(s) for user_id=%d",
                len(old_sessions),
                user_id,
            )
