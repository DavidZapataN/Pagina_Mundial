"""
Property-based tests for the matches module.

Covers:
  Property 4:  Match data round-trip
  Property 5:  Result registration stores exact score
  Property 6:  Invalid scores always rejected

Requirements: 2.1, 2.4, 2.5
"""

from __future__ import annotations

from datetime import datetime

import app.models  # noqa: F401
import pytest
from app.exceptions import InvalidScoreError
from app.models import Match, MatchStatus, TournamentPhase
from app.modules.matches.service import MatchService
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlmodel import Session, SQLModel, create_engine

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

team_name = st.text(min_size=1, max_size=50,
                    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "Zs")))
phase_st = st.sampled_from(list(TournamentPhase))
non_neg_int = st.integers(min_value=0, max_value=20)
neg_int = st.integers(max_value=-1)

_KICKOFF = datetime(2026, 6, 20, 18, 0, 0)


def _make_svc():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    return MatchService(session), session, engine


# ---------------------------------------------------------------------------
# Property 4: Match data round-trip
# **Validates: Requirements 2.1**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 4: Match data round-trip
@given(home=team_name, away=team_name, phase=phase_st)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_match_data_round_trip(home, away, phase):
    """
    **Validates: Requirements 2.1**

    Saving a Match to the DB and then retrieving it must yield identical fields.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            match = Match(
                home_team=home,
                away_team=away,
                kickoff_time=_KICKOFF,
                phase=phase,
                status=MatchStatus.pendiente,
            )
            session.add(match)
            session.commit()
            match_id = match.id

        with Session(engine) as session:
            retrieved = session.get(Match, match_id)

        assert retrieved is not None
        assert retrieved.home_team == home
        assert retrieved.away_team == away
        assert retrieved.phase == phase
        assert retrieved.status == MatchStatus.pendiente
        assert retrieved.official_home_goals is None
        assert retrieved.official_away_goals is None
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 5: Result registration stores exact score
# **Validates: Requirements 2.4**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 5: Result registration stores exact score
@given(home_goals=non_neg_int, away_goals=non_neg_int)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_result_registration_stores_exact_score(home_goals, away_goals):
    """
    **Validates: Requirements 2.4**

    For any non-negative (home_goals, away_goals), registering them as the
    official result must store exactly those values and set status to 'finalizado'.
    """
    svc, session, engine = _make_svc()
    try:
        match = Match(
            home_team="A", away_team="B",
            kickoff_time=_KICKOFF, phase=TournamentPhase.grupos,
        )
        session.add(match)
        session.commit()
        match_id = match.id

        result_match, _ = svc.register_result(match_id, home_goals, away_goals)

        assert result_match.status == MatchStatus.finalizado
        assert result_match.official_home_goals == home_goals
        assert result_match.official_away_goals == away_goals
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 6: Invalid scores always rejected
# **Validates: Requirements 2.5**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 6: Invalid scores always rejected
@given(
    home_goals=st.one_of(neg_int, non_neg_int),
    away_goals=st.one_of(neg_int, non_neg_int),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_invalid_scores_always_rejected(home_goals, away_goals):
    """
    **Validates: Requirements 2.5**

    If at least one goal value is negative, register_result must raise
    InvalidScoreError and leave the match unchanged.
    """
    if home_goals >= 0 and away_goals >= 0:
        return  # valid case — skip

    svc, session, engine = _make_svc()
    try:
        match = Match(
            home_team="A", away_team="B",
            kickoff_time=_KICKOFF, phase=TournamentPhase.grupos,
        )
        session.add(match)
        session.commit()
        match_id = match.id
        original_status = match.status

        with pytest.raises(InvalidScoreError):
            svc.register_result(match_id, home_goals, away_goals)

        session.expire_all()
        unchanged = session.get(Match, match_id)
        assert unchanged.status == original_status, "Match status must not change after an invalid score"
        assert unchanged.official_home_goals is None
        assert unchanged.official_away_goals is None
    finally:
        session.close()
        engine.dispose()
