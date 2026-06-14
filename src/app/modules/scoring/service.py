"""
ScoringService — lógica de puntuación para Polla del Mundial.

Reglas:
  - Marcador exacto  → 5 puntos
  - Ganador correcto → 3 puntos
  - Todo incorrecto  → 0 puntos

El método `calculate_and_persist_scores` se ejecuta DENTRO de la transacción
atómica iniciada por MatchService.register_result, por lo que no hace commit
por sí solo.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 8.6, 8.7
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlmodel import Session, select

from app.models import Match, MatchStatus, Prediction, PredictedWinner, User

logger = logging.getLogger("polla.scoring")


@dataclass
class UserScore:
    user_id: int
    match_id: int
    points: int


@dataclass
class UserTotalScore:
    user_id: int
    username: str
    total_points: int
    winner_count: int
    exact_score_count: int


class ScoringService:
    """
    Servicio de puntuación.

    Recibe una sesión SQLModel inyectada para poder participar en la
    transacción atómica de registro de resultado.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Función pura de puntuación (fácilmente testeable sin BD)
    # ------------------------------------------------------------------

    @staticmethod
    def score_prediction(
        predicted_winner: str,
        pred_home: int,
        pred_away: int,
        official_home: int,
        official_away: int,
        official_winner: str | None = None,
    ) -> int:
        """
        Retorna 5, 3 o 0 según las reglas de puntuación.

        Es una función pura — no accede a la base de datos.

        Regla de eliminatorias definidas por penales (modelo "híbrido"): el
        marcador guardado es el de los 120' (un empate), y ``official_winner``
        indica quién avanzó por penales. Para no perjudicar a nadie, se da el
        acierto de resultado (+3) tanto a quien predijo el resultado del
        marcador (el empate) como a quien predijo al equipo que avanzó. Solo
        queda en 0 quien apostó por el equipo eliminado.

        En fase de grupos ``official_winner`` es ``None`` y todo se deriva del
        marcador, sin cambios de comportamiento.

        Requirements: 4.2, 4.3, 4.4
        """
        if pred_home == official_home and pred_away == official_away:
            return 5

        # Acierto del resultado según el marcador (p. ej. empate en 120').
        if predicted_winner == _official_winner(official_home, official_away):
            return 3
        # Acierto de quién avanzó por penales (solo eliminatorias).
        if official_winner and predicted_winner == official_winner:
            return 3

        return 0

    # ------------------------------------------------------------------
    # Persistencia (dentro de transacción externa)
    # ------------------------------------------------------------------

    def calculate_and_persist_scores(
        self,
        match_id: int,
        official_home: int,
        official_away: int,
        official_winner: str | None = None,
    ) -> list[UserScore]:
        """
        Calcula y persiste los puntos de todos los usuarios que predijeron
        el partido *match_id*.

        Debe invocarse dentro de una transacción atómica externa —
        no llama a commit.

        Si falla el cálculo para un usuario específico, registra el error,
        asigna 0 puntos a ese usuario y continúa con los demás.

        Requirements: 4.1, 4.2, 4.3, 4.4, 4.6, 4.7
        """
        predictions = self._session.exec(
            select(Prediction).where(Prediction.match_id == match_id)
        ).all()

        results: list[UserScore] = []

        for pred in predictions:
            try:
                pts = self.score_prediction(
                    predicted_winner=pred.predicted_winner,
                    pred_home=pred.pred_home_goals,
                    pred_away=pred.pred_away_goals,
                    official_home=official_home,
                    official_away=official_away,
                    official_winner=official_winner,
                )
            except Exception as exc:
                logger.error(
                    "Error al calcular puntos para user_id=%d match_id=%d: %s",
                    pred.user_id,
                    match_id,
                    exc,
                )
                pts = 0

            pred.points = pts
            self._session.add(pred)
            results.append(UserScore(user_id=pred.user_id, match_id=match_id, points=pts))
            logger.debug(
                "Puntos asignados: user_id=%d match_id=%d puntos=%d",
                pred.user_id,
                match_id,
                pts,
            )

        return results

    # ------------------------------------------------------------------
    # Consulta de totales
    # ------------------------------------------------------------------

    def get_user_total(self, user_id: int) -> UserTotalScore:
        """
        Retorna el puntaje total acumulado del usuario junto con los
        contadores de ganadores y marcadores exactos acertados.

        Requirements: 4.5
        """
        user = self._session.get(User, user_id)
        username = user.username if user else str(user_id)

        # Only count predictions for finalizado matches (points not None)
        predictions = self._session.exec(
            select(Prediction).where(
                Prediction.user_id == user_id,
                Prediction.points.is_not(None),
            )
        ).all()

        total = 0
        winners = 0
        exacts = 0
        for p in predictions:
            pts = p.points or 0
            total += pts
            if pts == 5:
                exacts += 1
            elif pts == 3:
                winners += 1

        return UserTotalScore(
            user_id=user_id,
            username=username,
            total_points=total,
            winner_count=winners,
            exact_score_count=exacts,
        )


# ---------------------------------------------------------------------------
# Module-level helper
# ---------------------------------------------------------------------------


def _official_winner(home: int, away: int) -> str:
    if home > away:
        return PredictedWinner.home
    if away > home:
        return PredictedWinner.away
    return PredictedWinner.draw
