"""
Database connection and session management for Polla del Mundial.

Provides:
- `engine`                — SQLAlchemy engine pointing at world_cup.db
- `create_db_and_tables()`— create all SQLModel tables on startup
- `atomic_transaction()`  — context manager: BEGIN → yield Session → COMMIT
                            on success; ROLLBACK + log + raise TransactionError
                            on any exception
- `get_session()`         — FastAPI dependency (generator) for Depends()

Requirements: 8.1, 8.2, 8.5, 8.6
"""

from __future__ import annotations

import logging
import traceback
from contextlib import contextmanager
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine

from app.config import settings
from app.exceptions import TransactionError

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

logger = logging.getLogger("polla.database")

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

# check_same_thread=False is required for SQLite when using FastAPI because
# the same connection may be accessed from multiple threads (e.g., background
# tasks).  SQLModel / SQLAlchemy manage thread-safety at the session level.
# Render provides postgres:// but SQLAlchemy 2.0 requires postgresql://
_database_url = settings.DATABASE_URL.replace("postgres://", "postgresql://", 1)

_connect_args = (
    {"check_same_thread": False}
    if _database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    _database_url,
    connect_args=_connect_args,
    echo=settings.DEBUG,  # logs SQL statements when DEBUG=True
)

# ---------------------------------------------------------------------------
# Table creation
# ---------------------------------------------------------------------------


def create_db_and_tables() -> None:
    """
    Create all database tables defined by SQLModel metadata.

    Safe to call multiple times — existing tables are not dropped or modified.
    Called once at application startup (see lifespan handler in main.py).

    Requirements: 8.1, 8.2
    """
    # Import models here to ensure their SQLModel metadata is registered
    # before SQLMetadata.create_all() is called.
    import app.models  # noqa: F401  (side-effect: registers table metadata)

    SQLModel.metadata.create_all(engine)
    logger.info("Database tables verified / created at: %s", settings.DATABASE_URL)


# ---------------------------------------------------------------------------
# Atomic transaction context manager
# ---------------------------------------------------------------------------


@contextmanager
def atomic_transaction() -> Generator[Session, None, None]:
    """
    Context manager that wraps database operations in a single transaction.

    Usage::

        with atomic_transaction() as session:
            session.add(some_model)
            # ... more operations ...
        # COMMIT happens here automatically

    On success the session is committed and closed.
    On any exception the session is rolled back, the error is logged with
    its full stack trace, and a TransactionError is raised so callers can
    handle it appropriately without exposing raw SQLAlchemy internals.

    Requirements: 8.5, 8.6
    """
    session = Session(engine)
    try:
        yield session
        session.commit()
        logger.debug("Transaction committed successfully.")
    except Exception as exc:
        session.rollback()
        logger.error(
            "Transaction rolled back due to an error.\n"
            "Exception type : %s\n"
            "Exception      : %s\n"
            "Stack trace    :\n%s",
            type(exc).__name__,
            exc,
            traceback.format_exc(),
        )
        raise TransactionError(
            f"Database transaction failed and was rolled back: {exc}"
        ) from exc
    finally:
        session.close()


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


def get_session() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session per request.

    Usage in a route::

        @router.get("/items")
        def list_items(session: Session = Depends(get_session)):
            ...

    The session is always closed after the request completes, even if an
    exception is raised.  Unlike `atomic_transaction`, this dependency does
    NOT auto-commit — routes are responsible for calling session.commit()
    when they want to persist changes, or for using `atomic_transaction`
    inside a service method for multi-table operations.

    Requirements: 8.1, 8.2
    """
    with Session(engine) as session:
        yield session
