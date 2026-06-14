"""
Property-based tests for the scoring module.

Covers:
  Property 11: All predictors are scored
  Property 12: Scoring function correctness
  Property 13: Total score equals sum of individual scores

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
"""

from __future__ import annotations

from datetime import datetime

import app.models  # noqa: F401
from app.models import Match, MatchStatus, Prediction, PredictedWinner, TournamentPhase, User
from app.modules.scoring.service import ScoringService, _official_winner
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlmodel import Session, SQLModel, create_engine, select

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

goals_st = st.integers(min_value=0, max_value=15)
winner_st = st.sampled_from(list(PredictedWinner))
_KICKOFF = datetime(2026, 7, 10, 20, 0, 0)


def _setup():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    return session, engine


def _add_user(session, username) -> User:
    import bcrypt
    user = User(username=username, password_hash=bcrypt.hashpw(b"x", bcrypt.gensalt()).decode())
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _add_pending_match(session) -> Match:
    match = Match(
        home_team="A", away_team="B",
        kickoff_time=_KICKOFF, phase=TournamentPhase.grupos,
        status=MatchStatus.pendiente,
    )
    session.add(match)
    session.commit()
    session.refresh(match)
    return match


def _add_prediction(session, user_id, match_id, winner, home, away) -> Prediction:
    pred = Prediction(
        user_id=user_id, match_id=match_id,
        predicted_winner=winner,
        pred_home_goals=home, pred_away_goals=away,
    )
    session.add(pred)
    session.commit()
    session.refresh(pred)
    return pred


# ---------------------------------------------------------------------------
# Property 11: All predictors are scored
# **Validates: Requirements 4.1**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 11: All predictors are scored
@given(
    official_home=goals_st,
    official_away=goals_st,
    n_users=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_all_predictors_are_scored(official_home, official_away, n_users):
    """
    **Validates: Requirements 4.1**

    After calculate_and_persist_scores(), every user who had a prediction
    must have a non-null points value.
    """
    session, engine = _setup()
    try:
        match = _add_pending_match(session)
        users = [_add_user(session, f"u{i}_{id(session)}") for i in range(n_users)]

        # Add a prediction for each user
        for u in users:
            _add_prediction(session, u.id, match.id,
                             PredictedWinner.home, 1, 0)

        svc = ScoringService(session)
        results = svc.calculate_and_persist_scores(match.id, official_home, official_away)

        assert len(results) == n_users, "Must return one score entry per predictor"
        for r in results:
            assert r.points is not None, "points must be non-null after scoring"

        # Verify DB state
        preds = session.exec(
            select(Prediction).where(Prediction.match_id == match.id)
        ).all()
        for p in preds:
            assert p.points is not None, "DB prediction.points must be set after scoring"
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 12: Scoring function correctness
# **Validates: Requirements 4.2, 4.3, 4.4**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 12: Scoring function correctness
@given(
    pred_home=goals_st,
    pred_away=goals_st,
    official_home=goals_st,
    official_away=goals_st,
)
@settings(max_examples=100, deadline=None)
def test_scoring_function_correctness(pred_home, pred_away, official_home, official_away):
    """
    **Validates: Requirements 4.2, 4.3, 4.4**

    score_prediction() must return 5 for exact match, 3 for correct winner,
    and 0 otherwise. The predicted_winner is derived consistently from the
    predicted goals so the draw-consistency invariant is always satisfied.
    """
    # Derive a consistent predicted_winner from goals
    predicted_winner = _official_winner(pred_home, pred_away)

    pts = ScoringService.score_prediction(
        predicted_winner=predicted_winner,
        pred_home=pred_home,
        pred_away=pred_away,
        official_home=official_home,
        official_away=official_away,
    )

    official_winner = _official_winner(official_home, official_away)

    if pred_home == official_home and pred_away == official_away:
        assert pts == 5, f"Expected 5 for exact match, got {pts}"
    elif predicted_winner == official_winner:
        assert pts == 3, f"Expected 3 for correct winner, got {pts}"
    else:
        assert pts == 0, f"Expected 0 for wrong winner, got {pts}"


# ---------------------------------------------------------------------------
# Property 13: Total score equals sum of individual scores
# **Validates: Requirements 4.5, 4.6**
# ---------------------------------------------------------------------------

# Feature: world-cup-pool, Property 13: Total score equals sum of individual scores
@given(
    n_matches=st.integers(min_value=1, max_value=6),
    official_scores=st.lists(
        st.tuples(goals_st, goals_st), min_size=1, max_size=6
    ),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
def test_total_score_equals_sum_of_individual_scores(n_matches, official_scores):
    """
    **Validates: Requirements 4.5, 4.6**

    get_user_total() must equal the arithmetic sum of points on all the
    user's predictions for finished matches.
    """
    session, engine = _setup()
    try:
        user = _add_user(session, "scorer_user")
        total_expected = 0

        for i, (off_home, off_away) in enumerate(official_scores[:n_matches]):
            match = _add_pending_match(session)
            # always predict home wins 1-0 for simplicity
            _add_prediction(session, user.id, match.id, PredictedWinner.home, 1, 0)

            # Score it
            svc = ScoringService(session)
            results = svc.calculate_and_persist_scores(match.id, off_home, off_away)
            pts = next(r.points for r in results if r.user_id == user.id)
            total_expected += pts

            # Also mark the match as finalizado so it counts
            match.status = MatchStatus.finalizado
            match.official_home_goals = off_home
            match.official_away_goals = off_away
            session.add(match)
            session.commit()

        from app.modules.scoring.service import ScoringService as SS
        svc2 = SS(session)
        total_obj = svc2.get_user_total(user.id)

        assert total_obj.total_points == total_expected, (
            f"Total mismatch: expected {total_expected}, got {total_obj.total_points}"
        )
    finally:
        session.close()
        engine.dispose()
