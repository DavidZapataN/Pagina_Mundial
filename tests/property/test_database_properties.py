"""
Property-based tests for the database layer — persistence and atomicity.

Covers:
  Property 18: Data persistence across restarts
  Property 19: Synchronous write confirmation
  Property 20: Transaction atomicity

Requirements: 8.1, 8.2, 8.3, 8.5, 8.6, 8.7
Testing framework: Hypothesis (https://hypothesis.readthedocs.io/)
"""

from __future__ import annotations

import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlmodel import Session, SQLModel, create_engine, select

# Ensure all model metadata is registered before any engine is created
import app.models  # noqa: F401
from app.database import atomic_transaction
from app.exceptions import TransactionError
from app.models import Match, MatchStatus, TournamentPhase, User

# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

# Alphanumeric text suitable for team names and usernames (1–50 chars)
alphanumeric_text = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
)

# Valid TournamentPhase values
tournament_phase = st.sampled_from(list(TournamentPhase))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine(db_url: str):
    """Create a fresh SQLAlchemy/SQLModel engine and initialise all tables."""
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def _future_kickoff() -> datetime:
    """Return a fixed future kickoff time."""
    return datetime(2026, 6, 15, 18, 0, 0)


def _unique_db_path(base_dir: Path, prefix: str) -> Path:
    """
    Build a unique SQLite file path inside base_dir using a UUID.

    Using a unique file per Hypothesis example guarantees full isolation even
    though tmp_path is reused across examples within a single test invocation.
    Returns a Path object so callers can build the URL correctly for their OS.
    """
    unique_name = f"{prefix}_{uuid.uuid4().hex}.db"
    return base_dir / unique_name


def _sqlite_url(db_path: Path) -> str:
    """
    Build a SQLAlchemy SQLite URL from an absolute path in a cross-platform way.

    SQLAlchemy requires:
      - Unix/Mac:   sqlite:////absolute/path/file.db  (4 slashes total)
      - Windows:    sqlite:///C:\\path\\file.db        (3 slashes + drive letter)

    Using Path.as_posix() + the platform check avoids the double-drive issue
    that occurs when naively prepending '////' to a Windows absolute path.
    """
    import platform

    if platform.system() == "Windows":
        # SQLAlchemy on Windows: three slashes followed by the drive-letter path
        return f"sqlite:///{db_path}"
    else:
        # Unix: four slashes (three from the scheme separator + one for root /)
        return f"sqlite:////{db_path}"


# ---------------------------------------------------------------------------
# Property 18: Data persistence across restarts
# **Validates: Requirements 8.1, 8.2**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 18: Data persistence across restarts
@given(
    home_team=alphanumeric_text,
    away_team=alphanumeric_text,
    phase=tournament_phase,
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,  # File-based SQLite I/O exceeds the default 200ms deadline
)
def test_data_persists_across_restarts(tmp_path, home_team, away_team, phase):
    """
    **Validates: Requirements 8.1, 8.2**

    For any data successfully written to the database, closing and reopening
    the SQLite connection (simulating a server restart) SHALL produce the same
    data upon subsequent reads — no data is lost between sessions.
    """
    db_url = _sqlite_url(_unique_db_path(tmp_path, 'restart'))

    # --- First connection: write data ---
    engine_write = _make_engine(db_url)
    match = Match(
        home_team=home_team,
        away_team=away_team,
        kickoff_time=_future_kickoff(),
        phase=phase,
        status=MatchStatus.pendiente,
    )
    with Session(engine_write) as session:
        session.add(match)
        session.commit()
        session.refresh(match)
        written_id = match.id
    engine_write.dispose()

    # --- Second connection: verify persistence (simulated restart) ---
    engine_read = _make_engine(db_url)
    with Session(engine_read) as session:
        retrieved = session.get(Match, written_id)
    engine_read.dispose()

    assert retrieved is not None, (
        "Match was not found after reopening the database"
    )
    assert retrieved.home_team == home_team, (
        f"home_team mismatch after restart: expected {home_team!r}, got {retrieved.home_team!r}"
    )
    assert retrieved.away_team == away_team, (
        f"away_team mismatch after restart: expected {away_team!r}, got {retrieved.away_team!r}"
    )
    assert retrieved.phase == phase, (
        f"phase mismatch after restart: expected {phase!r}, got {retrieved.phase!r}"
    )
    assert retrieved.status == MatchStatus.pendiente, (
        f"status mismatch after restart: expected pendiente, got {retrieved.status!r}"
    )


# ---------------------------------------------------------------------------
# Property 19: Synchronous write confirmation
# **Validates: Requirements 8.3**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 19: Synchronous write confirmation
@given(
    home_team=alphanumeric_text,
    away_team=alphanumeric_text,
    phase=tournament_phase,
)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,  # File-based SQLite I/O exceeds the default 200ms deadline
)
def test_synchronous_write_confirmation(tmp_path, home_team, away_team, phase):
    """
    **Validates: Requirements 8.3**

    After a successful write (save a Match), immediately querying the database
    in a NEW connection to the same DB (using sqlite:////<path> format) SHALL
    return that record — no eventual consistency delays are permitted.
    """
    db_path = _unique_db_path(tmp_path, "sync")
    # Use the platform-appropriate SQLite URL (four-slash on Unix, three-slash
    # + drive letter on Windows) — satisfies the sqlite:////<path> intent from
    # the spec while being correct on both platforms.
    db_url = _sqlite_url(db_path)

    # --- First connection: write ---
    engine_write = _make_engine(db_url)
    match = Match(
        home_team=home_team,
        away_team=away_team,
        kickoff_time=_future_kickoff(),
        phase=phase,
        status=MatchStatus.pendiente,
    )
    with Session(engine_write) as session:
        session.add(match)
        session.commit()
        session.refresh(match)
        written_id = match.id
    engine_write.dispose()

    # --- New independent connection: immediately verify visibility ---
    engine_verify = _make_engine(db_url)
    with Session(engine_verify) as session:
        result = session.get(Match, written_id)
    engine_verify.dispose()

    assert result is not None, (
        "Match written by the first connection was not visible in a new "
        "connection immediately after commit (synchronous write guarantee violated)"
    )
    assert result.home_team == home_team
    assert result.away_team == away_team
    assert result.phase == phase


# ---------------------------------------------------------------------------
# Property 20: Transaction atomicity
# **Validates: Requirements 8.5, 8.6, 8.7**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 20: Transaction atomicity
@given(username=alphanumeric_text)
@settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,  # File-based SQLite I/O exceeds the default 200ms deadline
)
def test_transaction_atomicity(tmp_path, username):
    """
    **Validates: Requirements 8.5, 8.6, 8.7**

    For any multi-table operation, if any step fails mid-transaction, the
    database state SHALL be identical to the state before the operation began
    — no partial writes shall persist.

    Simulation: write a User then raise an exception before committing.
    Verification: after the failure, the User was NOT persisted.
    """
    db_url = _sqlite_url(_unique_db_path(tmp_path, "atomicity"))

    # Temporarily patch the global engine used by atomic_transaction()
    import app.database as db_module

    original_engine = db_module.engine
    test_engine = _make_engine(db_url)
    db_module.engine = test_engine

    try:
        # Baseline: count rows before the failed transaction
        with Session(test_engine) as session:
            count_before = len(session.exec(select(User)).all())

        # Attempt a transaction that deliberately fails mid-way
        with pytest.raises(TransactionError):
            with atomic_transaction() as session:
                user = User(
                    username=username,
                    password_hash="bcrypt_placeholder_hash",
                )
                session.add(user)
                # flush() sends the INSERT to the DB within the transaction
                # but does NOT commit — the rollback must undo this
                session.flush()
                # Simulate a failure BEFORE the context manager commits
                raise RuntimeError("Simulated mid-transaction failure")

        # After the failed transaction the row count must be unchanged
        with Session(test_engine) as session:
            count_after = len(session.exec(select(User)).all())

        assert count_after == count_before, (
            f"Transaction atomicity violated: {count_after - count_before} user(s) "
            f"were persisted despite a mid-transaction failure. "
            f"Before: {count_before}, After: {count_after}"
        )

        # Also verify by username — the specific user must not exist
        with Session(test_engine) as session:
            persisted = session.exec(
                select(User).where(User.username == username)
            ).first()

        assert persisted is None, (
            f"User with username {username!r} was found in the database "
            f"after a rolled-back transaction (partial write persisted)"
        )

    finally:
        # Always restore the original global engine
        db_module.engine = original_engine
        test_engine.dispose()
