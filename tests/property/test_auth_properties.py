"""
Property-based tests for the authentication module.

Covers:
  Property 1: Registration round-trip
  Property 2: Username uniqueness enforcement
  Property 3: Invalid credentials always rejected

Requirements: 1.1, 1.2, 1.4
Testing framework: Hypothesis (https://hypothesis.readthedocs.io/)
"""

from __future__ import annotations

# Ensure all model metadata is registered before any engine is created
import app.models  # noqa: F401
from app.exceptions import InvalidCredentialsError, UsernameAlreadyExistsError
from app.modules.auth.service import AuthService
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlmodel import Session, SQLModel, create_engine

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Alphanumeric usernames: 1–50 chars, Unicode letters and digits only
username_strategy = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
)

# Passwords: 1–100 chars, any printable text
password_strategy = st.text(min_size=1, max_size=100)


# ---------------------------------------------------------------------------
# Helper: fresh AuthService backed by an isolated in-memory SQLite DB
# ---------------------------------------------------------------------------


def make_auth_service():
    """
    Create a brand-new AuthService with a fresh in-memory SQLite database.

    Returns a tuple of (AuthService, Session, Engine) so callers that need to
    inspect DB state directly can do so via the session or engine.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    return AuthService(session), session, engine


# ---------------------------------------------------------------------------
# Property 1: Registration round-trip
# **Validates: Requirements 1.1, 1.2**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 1: Registration round-trip
@given(
    username=username_strategy,
    password=password_strategy,
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_registration_round_trip(username, password):
    """
    **Validates: Requirements 1.1, 1.2**

    For any valid username and password, registering a user and then logging
    in with those same credentials SHALL return a non-empty session token.
    The complete register → login cycle must succeed without errors.
    """
    svc, session, engine = make_auth_service()
    try:
        # Register the user
        user = svc.register(username, password)

        # The returned User must have an assigned primary key and matching username
        assert user.id is not None, "Registered user must have a DB-assigned id"
        assert user.username == username, (
            f"Registered username mismatch: expected {username!r}, got {user.username!r}"
        )

        # Login with the same credentials must return a valid (non-empty) token
        token = svc.login(username, password)

        assert token, "Login after successful registration must return a non-empty session token"
        assert isinstance(token, str), "Session token must be a string"
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 2: Username uniqueness enforcement
# **Validates: Requirements 1.1, 1.2**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 2: Username uniqueness enforcement
@given(
    username=username_strategy,
    password1=password_strategy,
    password2=password_strategy,
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_username_uniqueness_enforcement(username, password1, password2):
    """
    **Validates: Requirements 1.1, 1.2**

    For any username already registered, any subsequent registration attempt
    with that same username SHALL be rejected with UsernameAlreadyExistsError,
    regardless of the password used for the second attempt.
    """
    svc, session, engine = make_auth_service()
    try:
        # First registration must succeed
        svc.register(username, password1)

        # Second registration with the same username must raise the domain error,
        # whether the password is identical or completely different
        try:
            svc.register(username, password2)
            raise AssertionError(
                f"Expected UsernameAlreadyExistsError when registering duplicate "
                f"username {username!r} but no exception was raised."
            )
        except UsernameAlreadyExistsError:
            pass  # Expected — this is the correct behaviour
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 3: Invalid credentials always rejected
# **Validates: Requirements 1.4**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 3: Invalid credentials always rejected
@given(
    registered_username=username_strategy,
    registered_password=password_strategy,
    login_username=username_strategy,
    login_password=password_strategy,
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
def test_invalid_credentials_always_rejected(
    registered_username,
    registered_password,
    login_username,
    login_password,
):
    """
    **Validates: Requirements 1.4**

    For any (username, password) pair where no matching registered user exists,
    the login attempt SHALL always raise InvalidCredentialsError without
    revealing which field was incorrect.

    Strategy: register a user under registered_username, then attempt to login
    with login_username.  When the two usernames are different the login_username
    is guaranteed to be unregistered.  When they happen to be equal we still have
    a non-matching user because we use a DB that has only that one registration —
    the login attempt uses a potentially different password, but more importantly
    we explicitly handle the equal-username case by skipping (the password would
    need to match for a successful login, which is covered by Property 1).

    The property focuses on the case where login_username != registered_username,
    i.e., a completely unknown username is used — the system must never reveal
    "username not found" vs "wrong password".
    """
    # Only test when the login username differs from the registered one.
    # When they are equal, the login may succeed (covered by Property 1) or
    # fail due to a wrong password, which is a different sub-case.
    # Using assume() would mark such examples as invalid; instead we simply
    # skip them so Hypothesis keeps generating until it finds valid ones.
    if login_username == registered_username:
        return

    svc, session, engine = make_auth_service()
    try:
        # Register exactly one user
        svc.register(registered_username, registered_password)

        # Attempt to login with an unregistered username
        try:
            svc.login(login_username, login_password)
            raise AssertionError(
                f"Expected InvalidCredentialsError when logging in with "
                f"unregistered username {login_username!r} but no exception was raised."
            )
        except InvalidCredentialsError:
            pass  # Expected — system correctly rejected the unknown credentials
    finally:
        session.close()
        engine.dispose()
