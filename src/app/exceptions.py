"""
Domain exception hierarchy for Polla del Mundial.

All application-specific exceptions derive from PollaError so callers can
catch the base class when they need to handle any application error uniformly,
or catch a specific subclass for finer-grained handling.

Exception hierarchy:
    PollaError (base)
    ├── AuthError
    │   ├── UsernameAlreadyExistsError
    │   ├── InvalidCredentialsError
    │   └── UnauthenticatedError
    ├── MatchError
    │   ├── MatchNotFoundError
    │   └── InvalidScoreError
    ├── PredictionError
    │   ├── MatchClosedError
    │   └── DrawMismatchError
    └── DatabaseError
        └── TransactionError
"""


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class PollaError(Exception):
    """Base exception for all Polla del Mundial domain errors."""


# ---------------------------------------------------------------------------
# Authentication errors
# ---------------------------------------------------------------------------


class AuthError(PollaError):
    """Base for authentication and authorisation errors."""


class UsernameAlreadyExistsError(AuthError):
    """Raised when a registration attempt uses an already-taken username."""


class InvalidCredentialsError(AuthError):
    """Raised when login credentials do not match any registered user."""


class UnauthenticatedError(AuthError):
    """Raised when an action requires an authenticated session but none exists."""


# ---------------------------------------------------------------------------
# Match errors
# ---------------------------------------------------------------------------


class MatchError(PollaError):
    """Base for match-related errors."""


class MatchNotFoundError(MatchError):
    """Raised when a requested match does not exist in the database."""


class InvalidScoreError(MatchError):
    """Raised when an official score contains negative or non-numeric values."""


# ---------------------------------------------------------------------------
# Prediction errors
# ---------------------------------------------------------------------------


class PredictionError(PollaError):
    """Base for prediction-related errors."""


class MatchClosedError(PredictionError):
    """Raised when a prediction is attempted for a match that is no longer pending."""


class DrawMismatchError(PredictionError):
    """
    Raised when a prediction's scoreline implies a draw (equal goals) but
    the predicted winner is not 'draw', or vice-versa.
    """


# ---------------------------------------------------------------------------
# Database errors
# ---------------------------------------------------------------------------


class DatabaseError(PollaError):
    """Base for database-layer errors."""


class TransactionError(DatabaseError):
    """
    Raised when a database transaction cannot be completed.

    The transaction has already been rolled back by the time this exception
    reaches the caller. Callers should treat the operation as a no-op and
    surface an appropriate error to the end user.
    """


# ---------------------------------------------------------------------------
# Group errors
# ---------------------------------------------------------------------------


class GroupError(PollaError):
    """Base for group-related errors."""


class GroupNotFoundError(GroupError):
    """Raised when no group matches the given join code."""


class AlreadyMemberError(GroupError):
    """Raised when user tries to join a group they already belong to."""
