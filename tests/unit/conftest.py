"""
Fixtures for unit tests — provides an isolated in-memory AuthService per test.
"""

import pytest
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 — registers all table metadata
from app.modules.auth.service import AuthService


@pytest.fixture
def auth_service():
    """
    Yield a fresh AuthService backed by an in-memory SQLite database.

    Each test receives its own engine + schema so there is no state leakage
    between tests.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        yield AuthService(session)

    SQLModel.metadata.drop_all(engine)
    engine.dispose()
