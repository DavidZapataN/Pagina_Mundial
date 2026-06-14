"""
LeaderboardService — tabla de posiciones de Polla del Mundial.

Calcula y retorna la tabla de posiciones ordenada:
  1. Puntaje total (descendente)
  2. Marcadores exactos (descendente)
  3. Nombre de usuario (ascendente)

Requirements: 5.1, 5.2, 5.3
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlmodel import Session, select

from app.models import Match, Prediction, TournamentPhase, User

logger = logging.getLogger("polla.leaderboard")


@dataclass
class LeaderboardEntry:
    position: int
    user_id: int
    username: str
    total_points: int
    winner_count: int
    exact_score_count: int


class LeaderboardService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_leaderboard(self) -> list[LeaderboardEntry]:
        return self.get_leaderboard_filtered()

    def get_leaderboard_filtered(
        self,
        user_ids: set[int] | None = None,
        min_phase: TournamentPhase | None = None,
    ) -> list[LeaderboardEntry]:
        users = self._session.exec(select(User)).all()
        if user_ids is not None:
            users = [u for u in users if u.id in user_ids]

        # Los puntos bonus (campeón/goleador) aplican al torneo completo, no a
        # una fase específica: solo se suman cuando no hay filtro de fase.
        bonus_map: dict[int, int] = {}
        if min_phase is None:
            from app.modules.bonus.service import BonusService
            bonus_map = BonusService(self._session).user_points_map()

        entries = []
        for user in users:
            if min_phase is not None:
                total, winners, exacts = self._compute_scores_from_phase(user.id, min_phase)
            else:
                total, winners, exacts = self._compute_scores(user.id)
                total += bonus_map.get(user.id, 0)
            entries.append(
                LeaderboardEntry(
                    position=0,
                    user_id=user.id,  # type: ignore[arg-type]
                    username=user.username,
                    total_points=total,
                    winner_count=winners,
                    exact_score_count=exacts,
                )
            )

        entries.sort(key=lambda e: (-e.total_points, -e.exact_score_count, e.username))
        for i, entry in enumerate(entries, start=1):
            entry.position = i

        return entries

    def get_user_rank(self, user_id: int) -> LeaderboardEntry | None:
        board = self.get_leaderboard()
        for entry in board:
            if entry.user_id == user_id:
                return entry
        return None

    def _compute_scores(self, user_id: int) -> tuple[int, int, int]:
        predictions = self._session.exec(
            select(Prediction).where(
                Prediction.user_id == user_id,
                Prediction.points.is_not(None),
            )
        ).all()
        return self._tally(predictions)

    def _compute_scores_from_phase(self, user_id: int, min_phase: TournamentPhase) -> tuple[int, int, int]:
        phase_order = list(TournamentPhase)
        min_idx = phase_order.index(min_phase)
        valid_values = [p.value for p in phase_order[min_idx:]]

        rows = self._session.exec(
            select(Prediction, Match)
            .join(Match, Prediction.match_id == Match.id)  # type: ignore[arg-type]
            .where(
                Prediction.user_id == user_id,
                Prediction.points.is_not(None),
                Match.phase.in_(valid_values),
            )
        ).all()

        total = winners = exacts = 0
        for pred, _match in rows:
            pts = pred.points or 0
            total += pts
            if pts == 5:
                exacts += 1
            elif pts == 3:
                winners += 1
        return total, winners, exacts

    @staticmethod
    def _tally(predictions: list[Prediction]) -> tuple[int, int, int]:
        total = winners = exacts = 0
        for p in predictions:
            pts = p.points or 0
            total += pts
            if pts == 5:
                exacts += 1
            elif pts == 3:
                winners += 1
        return total, winners, exacts
