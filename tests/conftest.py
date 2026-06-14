"""
Shared pytest fixtures for Polla del Mundial test suite.
"""

import pytest
from sqlmodel import Session, SQLModel, create_engine

# Ensure all table metadata is registered before creating tables
import app.models  # noqa: F401


@pytest.fixture
def in_memory_engine():
    """
    Creates a SQLite in-memory engine with all tables.

    Provides an isolated, fast engine suitable for tests that do not need
    persistence across connections (e.g., unit logic tests, scoring tests).
    The engine is torn down after the test completes.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)
    engine.dispose()
