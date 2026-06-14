"""
PredictionService — lógica de dominio para predicciones de usuarios.

Responsabilidades:
- Registrar o actualizar predicciones (UPSERT)
- Validar cierre de partido y consistencia empate/ganador
- Consultar historial y estado de predicciones

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 6.1, 6.2, 6.3
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

_CUTOFF_MINUTES = 15

from sqlmodel import Session, select

from app.exceptions import DrawMismatchError, MatchClosedError, MatchNotFoundError
from app.models import Match, MatchStatus, Prediction, PredictedWinner, TournamentPhase
from app.utils import utcnow

logger = logging.getLogger("polla.predictions")

PredictionStatus = Literal["sin_prediccion", "prediccion_registrada", "cerrado"]
ResultClassification = Literal["marcador_exacto", "ganador_acertado", "fallida", "pendiente"]


@dataclass
class PredictionWithResult:
    prediction: Prediction
    match: Match
    result_classification: ResultClassification


class PredictionService:
    """
    Servicio de predicciones.

    Recibe una sesión SQLModel inyectada para controlar el ciclo de vida
    de la transacción desde el caller (FastAPI dependency, test fixture).
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Escribir predicciones
    # ------------------------------------------------------------------

    def save_prediction(
        self,
        user_id: int,
        match_id: int,
        predicted_winner: PredictedWinner,
        home_goals: int,
        away_goals: int,
    ) -> Prediction:
        """
        Registra o actualiza la predicción de un usuario para un partido.

        - Solo se permite cuando el partido está en estado «pendiente».
        - Si home_goals == away_goals el predicted_winner debe ser «draw».
        - Si ya existe una predicción del usuario para ese partido, la actualiza.

        Raises:
            MatchNotFoundError:  el partido no existe.
            MatchClosedError:    el partido no está en estado «pendiente».
            DrawMismatchError:   goles iguales pero ganador != draw (o viceversa).

        Requirements: 3.1, 3.2, 3.3, 3.4, 3.6
        """
        match = self._session.get(Match, match_id)
        if match is None:
            raise MatchNotFoundError(f"No se encontró el partido con ID {match_id}")

        if match.status != MatchStatus.pendiente:
            raise MatchClosedError(
                "Las predicciones para este partido ya están cerradas"
            )

        cutoff = match.kickoff_time - timedelta(minutes=_CUTOFF_MINUTES)
        if utcnow() >= cutoff:
            raise MatchClosedError(
                f"Las predicciones cierran {_CUTOFF_MINUTES} minutos antes del partido"
            )

        self._validate_draw_consistency(predicted_winner, home_goals, away_goals)

        # UPSERT: look for an existing prediction
        existing = self._session.exec(
            select(Prediction).where(
                Prediction.user_id == user_id,
                Prediction.match_id == match_id,
            )
        ).first()

        if existing is not None:
            existing.predicted_winner = predicted_winner
            existing.pred_home_goals = home_goals
            existing.pred_away_goals = away_goals
            existing.updated_at = utcnow()
            self._session.add(existing)
            self._session.commit()
            self._session.refresh(existing)
            logger.info(
                "Predicción actualizada: user_id=%d match_id=%d %d-%d (%s)",
                user_id, match_id, home_goals, away_goals, predicted_winner,
            )
            return existing

        prediction = Prediction(
            user_id=user_id,
            match_id=match_id,
            predicted_winner=predicted_winner,
            pred_home_goals=home_goals,
            pred_away_goals=away_goals,
        )
        self._session.add(prediction)
        self._session.commit()
        self._session.refresh(prediction)
        logger.info(
            "Predicción registrada: user_id=%d match_id=%d %d-%d (%s)",
            user_id, match_id, home_goals, away_goals, predicted_winner,
        )
        return prediction

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def get_user_predictions(self, user_id: int) -> list[PredictionWithResult]:
        """
        Retorna el historial completo de predicciones del usuario con el
        resultado y la clasificación del acierto cuando está disponible.

        Requirements: 3.6, 6.1, 6.2
        """
        predictions = self._session.exec(
            select(Prediction).where(Prediction.user_id == user_id)
        ).all()

        result: list[PredictionWithResult] = []
        for pred in predictions:
            match = self._session.get(Match, pred.match_id)
            if match is None:
                continue
            classification = self._classify(pred)
            result.append(
                PredictionWithResult(
                    prediction=pred,
                    match=match,
                    result_classification=classification,
                )
            )
        return result

    def get_prediction_status(self, user_id: int, match_id: int) -> PredictionStatus:
        """
        Retorna el estado de la predicción de un usuario para un partido:
          - «cerrado»              — partido no pendiente
          - «prediccion_registrada» — tiene predicción y partido pendiente
          - «sin_prediccion»       — sin predicción y partido pendiente

        Requirements: 3.7
        """
        match = self._session.get(Match, match_id)
        if match is None or match.status != MatchStatus.pendiente:
            return "cerrado"

        existing = self._session.exec(
            select(Prediction).where(
                Prediction.user_id == user_id,
                Prediction.match_id == match_id,
            )
        ).first()

        return "prediccion_registrada" if existing is not None else "sin_prediccion"

    def filter_by_phase(
        self, user_id: int, phase: TournamentPhase
    ) -> list[PredictionWithResult]:
        """
        Retorna las predicciones del usuario filtradas por fase del torneo.

        Requirements: 6.3
        """
        all_predictions = self.get_user_predictions(user_id)
        return [p for p in all_predictions if p.match.phase == phase]

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_draw_consistency(
        predicted_winner: PredictedWinner,
        home_goals: int,
        away_goals: int,
    ) -> None:
        """
        Verifica que la combinación (ganador, goles) sea coherente.

        Requirements: 3.3
        """
        is_draw_score = home_goals == away_goals
        is_draw_pick = predicted_winner == PredictedWinner.draw

        if is_draw_score and not is_draw_pick:
            raise DrawMismatchError(
                "El marcador indica empate; selecciona 'empate' como resultado"
            )
        if not is_draw_score and is_draw_pick:
            raise DrawMismatchError(
                "El marcador indica empate; selecciona 'empate' como resultado"
            )

    @staticmethod
    def _classify(prediction: Prediction) -> ResultClassification:
        """Clasifica una predicción según los puntos obtenidos."""
        if prediction.points is None:
            return "pendiente"
        if prediction.points == 5:
            return "marcador_exacto"
        if prediction.points == 3:
            return "ganador_acertado"
        return "fallida"
