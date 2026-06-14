"""
Property-based tests for the predictions module.

Covers:
  Property 7:  Prediction lock invariant
  Property 8:  Draw consistency validation
  Property 9:  Prediction persistence round-trip
  Property 10: Prediction status accuracy

Requirements: 3.1, 3.3, 3.4, 3.6, 3.7
"""

from __future__ import annotations

from datetime import datetime

import app.models  # noqa: F401
import pytest
from app.exceptions import DrawMismatchError, MatchClosedError
from app.models import Match, MatchStatus, Prediction, PredictedWinner, TournamentPhase, User
from app.modules.predictions.service import PredictionService
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlmodel import Session, SQLModel, create_engine, select

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

non_neg = st.integers(min_value=0, max_value=15)
_KICKOFF = datetime(2026, 7, 1, 20, 0, 0)

NON_PENDING = [MatchStatus.en_curso, MatchStatus.finalizado]


def _setup():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    return session, engine


def _add_user(session, username="player1") -> User:
    import bcrypt
    user = User(
        username=username,
        password_hash=bcrypt.hashpw(b"pass", bcrypt.gensalt()).decode(),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _add_match(session, status=MatchStatus.pendiente) -> Match:
    match = Match(
        home_team="Col", away_team="Bra",
        kickoff_time=_KICKOFF, phase=TournamentPhase.grupos, status=status,
    )
    session.add(match)
    session.commit()
    session.refresh(match)
    return match


# ---------------------------------------------------------------------------
# Property 7: Prediction lock invariant
# **Validates: Requirements 3.1, 3.4**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 7: Prediction lock invariant
@given(status=st.sampled_from(NON_PENDING))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_prediction_lock_invariant(status):
    """
    **Validates: Requirements 3.1, 3.4**

    For matches in 'en_curso' or 'finalizado', save_prediction must raise
    MatchClosedError. For 'pendiente' matches it must succeed.
    """
    session, engine = _setup()
    try:
        user = _add_user(session)
        match = _add_match(session, status=status)
        svc = PredictionService(session)

        with pytest.raises(MatchClosedError):
            svc.save_prediction(
                user_id=user.id,
                match_id=match.id,
                predicted_winner=PredictedWinner.home,
                home_goals=1,
                away_goals=0,
            )

        # Pending match must accept predictions
        pending_match = _add_match(session, status=MatchStatus.pendiente)
        pred = svc.save_prediction(
            user_id=user.id,
            match_id=pending_match.id,
            predicted_winner=PredictedWinner.home,
            home_goals=1,
            away_goals=0,
        )
        assert pred.id is not None
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 8: Draw consistency validation
# **Validates: Requirements 3.3**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 8: Draw consistency validation
@given(goals=non_neg)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_draw_consistency_validation(goals):
    """
    **Validates: Requirements 3.3**

    Equal goals with a non-draw pick must be rejected. Equal goals with
    draw pick must be accepted. Unequal goals with draw pick must be rejected.
    """
    session, engine = _setup()
    try:
        user = _add_user(session)
        svc = PredictionService(session)

        # Equal goals + non-draw winner → DrawMismatchError
        match1 = _add_match(session)
        with pytest.raises(DrawMismatchError):
            svc.save_prediction(
                user_id=user.id, match_id=match1.id,
                predicted_winner=PredictedWinner.home,
                home_goals=goals, away_goals=goals,
            )

        # Equal goals + draw winner → success
        match2 = _add_match(session)
        pred = svc.save_prediction(
            user_id=user.id, match_id=match2.id,
            predicted_winner=PredictedWinner.draw,
            home_goals=goals, away_goals=goals,
        )
        assert pred.id is not None

        # Unequal goals + draw winner → DrawMismatchError
        match3 = _add_match(session)
        with pytest.raises(DrawMismatchError):
            svc.save_prediction(
                user_id=user.id, match_id=match3.id,
                predicted_winner=PredictedWinner.draw,
                home_goals=goals, away_goals=goals + 1,
            )
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 9: Prediction persistence round-trip
# **Validates: Requirements 3.6, 6.1**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 9: Prediction persistence round-trip
@given(home_goals=non_neg, away_goals=non_neg)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_prediction_persistence_round_trip(home_goals, away_goals):
    """
    **Validates: Requirements 3.6, 6.1**

    After saving a prediction, get_user_predictions() must include it with
    all original field values intact.
    """
    if home_goals == away_goals:
        winner = PredictedWinner.draw
    elif home_goals > away_goals:
        winner = PredictedWinner.home
    else:
        winner = PredictedWinner.away

    session, engine = _setup()
    try:
        user = _add_user(session)
        match = _add_match(session)
        svc = PredictionService(session)

        svc.save_prediction(
            user_id=user.id, match_id=match.id,
            predicted_winner=winner,
            home_goals=home_goals, away_goals=away_goals,
        )

        history = svc.get_user_predictions(user.id)
        assert any(
            e.prediction.match_id == match.id
            and e.prediction.pred_home_goals == home_goals
            and e.prediction.pred_away_goals == away_goals
            and e.prediction.predicted_winner == winner
            for e in history
        ), "Saved prediction not found in get_user_predictions() result"
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 10: Prediction status accuracy
# **Validates: Requirements 3.7**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 10: Prediction status accuracy
@given(status=st.sampled_from(list(MatchStatus)))
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_prediction_status_accuracy(status):
    """
    **Validates: Requirements 3.7**

    get_prediction_status() must accurately reflect whether the user has
    a prediction and whether the match is still open.
    """
    session, engine = _setup()
    try:
        user = _add_user(session)
        match = _add_match(session, status=status)
        svc = PredictionService(session)

        if status != MatchStatus.pendiente:
            result = svc.get_prediction_status(user.id, match.id)
            assert result == "cerrado", f"Expected 'cerrado' for status={status}, got {result!r}"
        else:
            # No prediction yet
            result = svc.get_prediction_status(user.id, match.id)
            assert result == "sin_prediccion"

            # After saving a prediction
            svc.save_prediction(
                user_id=user.id, match_id=match.id,
                predicted_winner=PredictedWinner.home,
                home_goals=1, away_goals=0,
            )
            result = svc.get_prediction_status(user.id, match.id)
            assert result == "prediccion_registrada"
    finally:
        session.close()
        engine.dispose()
