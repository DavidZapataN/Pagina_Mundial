"""
Property-based tests for the leaderboard and prediction history modules.

Covers:
  Property 14: Leaderboard ordering with tie-breaking
  Property 15: Leaderboard entry completeness
  Property 16: Prediction result classification
  Property 17: Phase filter correctness

Requirements: 5.1, 5.2, 5.3, 6.2, 6.3
"""

from __future__ import annotations

from datetime import datetime

import app.models  # noqa: F401
from app.models import Match, MatchStatus, Prediction, PredictedWinner, TournamentPhase, User
from app.modules.leaderboard.service import LeaderboardService
from app.modules.predictions.service import PredictionService
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlmodel import Session, SQLModel, create_engine

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

goals_st = st.integers(min_value=0, max_value=10)
_KICKOFF = datetime(2026, 8, 1, 18, 0, 0)


def _setup():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    return session, engine


def _add_user(session, username) -> User:
    import bcrypt
    u = User(username=username, password_hash=bcrypt.hashpw(b"p", bcrypt.gensalt()).decode())
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _add_finished_prediction(session, user_id, match_id, points) -> Prediction:
    winner = PredictedWinner.home
    p = Prediction(
        user_id=user_id, match_id=match_id,
        predicted_winner=winner,
        pred_home_goals=1, pred_away_goals=0,
        points=points,
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


def _add_match(session, phase=TournamentPhase.grupos, status=MatchStatus.finalizado) -> Match:
    m = Match(
        home_team="X", away_team="Y",
        kickoff_time=_KICKOFF, phase=phase, status=status,
    )
    session.add(m)
    session.commit()
    session.refresh(m)
    return m


# ---------------------------------------------------------------------------
# Property 14: Leaderboard ordering with tie-breaking
# **Validates: Requirements 5.1, 5.2**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 14: Leaderboard ordering with tie-breaking
@given(n_users=st.integers(min_value=2, max_value=10))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_leaderboard_ordering_with_tie_breaking(n_users):
    """
    **Validates: Requirements 5.1, 5.2**

    The leaderboard must be sorted: total_points DESC, then
    exact_score_count DESC, then username ASC.
    """
    import random
    session, engine = _setup()
    try:
        match = _add_match(session)
        users = [_add_user(session, f"p{i:02d}") for i in range(n_users)]

        # Assign random points (0, 3, or 5) per user
        for u in users:
            pts = random.choice([0, 3, 5])
            _add_finished_prediction(session, u.id, match.id, pts)

        svc = LeaderboardService(session)
        board = svc.get_leaderboard()

        assert len(board) == n_users

        for i in range(len(board) - 1):
            a, b = board[i], board[i + 1]
            # Primary: total_points DESC
            assert a.total_points >= b.total_points, (
                f"Ordering violation at positions {a.position},{b.position}: "
                f"{a.total_points} < {b.total_points}"
            )
            if a.total_points == b.total_points:
                # Secondary: exact_score_count DESC
                assert a.exact_score_count >= b.exact_score_count, (
                    f"Tie-break violation: exact_score_count {a.exact_score_count} < {b.exact_score_count}"
                )
                if a.exact_score_count == b.exact_score_count:
                    # Tertiary: username ASC
                    assert a.username <= b.username, (
                        f"Username sort violation: {a.username!r} > {b.username!r}"
                    )
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 15: Leaderboard entry completeness
# **Validates: Requirements 5.3**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 15: Leaderboard entry completeness
@given(n_users=st.integers(min_value=1, max_value=8))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_leaderboard_entry_completeness(n_users):
    """
    **Validates: Requirements 5.3**

    Every leaderboard entry must contain all five required fields with
    non-None values.
    """
    session, engine = _setup()
    try:
        match = _add_match(session)
        users = [_add_user(session, f"q{i:02d}") for i in range(n_users)]
        for u in users:
            _add_finished_prediction(session, u.id, match.id, 3)

        svc = LeaderboardService(session)
        board = svc.get_leaderboard()

        for entry in board:
            assert entry.position is not None and entry.position > 0
            assert entry.username is not None and entry.username != ""
            assert entry.total_points is not None
            assert entry.winner_count is not None
            assert entry.exact_score_count is not None
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 16: Prediction result classification
# **Validates: Requirements 6.2**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 16: Prediction result classification
@given(points=st.sampled_from([0, 3, 5]))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_prediction_result_classification(points):
    """
    **Validates: Requirements 6.2**

    _classify() must map points→classification correctly.
    """
    from app.models import Prediction as P
    from app.modules.predictions.service import PredictionService as PS

    pred = Prediction(
        user_id=1, match_id=1,
        predicted_winner=PredictedWinner.home,
        pred_home_goals=1, pred_away_goals=0,
        points=points,
    )
    cls = PS._classify(pred)

    if points == 5:
        assert cls == "marcador_exacto"
    elif points == 3:
        assert cls == "ganador_acertado"
    else:
        assert cls == "fallida"


# ---------------------------------------------------------------------------
# Property 17: Phase filter correctness
# **Validates: Requirements 6.3**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 17: Phase filter correctness
@given(target_phase=st.sampled_from(list(TournamentPhase)))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_phase_filter_correctness(target_phase):
    """
    **Validates: Requirements 6.3**

    filter_by_phase(user_id, phase) must return ONLY predictions whose
    match.phase == target_phase — no cross-phase leakage.
    """
    session, engine = _setup()
    try:
        user = _add_user(session, "filter_user")
        svc = PredictionService(session)

        # Create one pending match per phase and add a prediction
        for phase in TournamentPhase:
            match = Match(
                home_team="A", away_team="B",
                kickoff_time=_KICKOFF, phase=phase, status=MatchStatus.pendiente,
            )
            session.add(match)
            session.commit()
            session.refresh(match)

            winner = PredictedWinner.home
            svc.save_prediction(
                user_id=user.id, match_id=match.id,
                predicted_winner=winner, home_goals=1, away_goals=0,
            )

        filtered = svc.filter_by_phase(user.id, target_phase)
        for entry in filtered:
            assert entry.match.phase == target_phase, (
                f"Expected phase {target_phase!r}, got {entry.match.phase!r}"
            )
    finally:
        session.close()
        engine.dispose()
