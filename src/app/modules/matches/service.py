"""
MatchService — lógica de dominio para el módulo de partidos.

Responsabilidades:
- Listar partidos agrupados por fecha o fase
- Obtener un partido por ID
- Actualizar el estado de un partido (usado por el scheduler)
- Registrar el resultado oficial de un partido

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from sqlmodel import Session, select

from app.exceptions import InvalidScoreError, MatchNotFoundError
from app.models import LIVE_WINDOW, Match, MatchStatus, PredictedWinner
from app.modules.scoring.service import ScoringService, UserScore
from app.utils import utcnow

logger = logging.getLogger("polla.matches")


class MatchService:
    """
    Servicio de partidos.  Recibe una sesión SQLModel por inyección de
    dependencias para poder participar en transacciones externas o ser
    llamado desde FastAPI via ``Depends(get_session)``.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def list_matches(self, group_by: Literal["date", "phase"] = "date") -> list[Match]:
        """
        Retorna todos los partidos ordenados según el criterio solicitado.

        - ``group_by="date"``  → ordenados por ``kickoff_time`` ascendente.
        - ``group_by="phase"`` → ordenados por ``phase`` ascendente,
          luego por ``kickoff_time`` ascendente dentro de cada fase.

        Requirements: 2.1, 2.2
        """
        statement = select(Match)

        if group_by == "phase":
            statement = statement.order_by(Match.phase, Match.kickoff_time)
        else:
            statement = statement.order_by(Match.kickoff_time)

        matches = self._session.exec(statement).all()
        return list(matches)

    def get_match(self, match_id: int) -> Match:
        """
        Retorna el partido con el ``match_id`` dado.

        Raises:
            MatchNotFoundError: si no existe ningún partido con ese ID.

        Requirements: 2.1
        """
        match = self._session.get(Match, match_id)
        if match is None:
            raise MatchNotFoundError(
                f"No se encontró el partido con ID {match_id}"
            )
        return match

    # ------------------------------------------------------------------
    # Mutaciones de estado
    # ------------------------------------------------------------------

    def update_status(self, match_id: int, new_status: MatchStatus) -> Match:
        """
        Actualiza el estado de un partido.

        Utilizado principalmente por el scheduler para la transición
        automática ``pendiente → en_curso`` cuando se alcanza
        ``kickoff_time``.

        Raises:
            MatchNotFoundError: si no existe ningún partido con ese ID.

        Requirements: 2.3
        """
        match = self.get_match(match_id)
        match.status = new_status
        self._session.add(match)
        self._session.commit()
        self._session.refresh(match)
        logger.info(
            "Partido %d: estado actualizado a '%s'.", match_id, new_status.value
        )
        return match

    def auto_transition_statuses(self, now: datetime | None = None) -> int:
        """
        Transición automática pendiente → en_curso para partidos cuyo
        kickoff ya pasó y siguen dentro de la ventana de juego.

        Idempotente y barato: solo escribe cuando hay cambios. Llamado desde
        la tarea de fondo y de forma perezosa al listar partidos.

        Returns: número de partidos transicionados.
        """
        now = now or utcnow()
        candidates = self._session.exec(
            select(Match).where(
                Match.status == MatchStatus.pendiente,
                Match.kickoff_time <= now,
                Match.kickoff_time >= now - LIVE_WINDOW,
            )
        ).all()
        changed = 0
        for m in candidates:
            m.status = MatchStatus.en_curso
            self._session.add(m)
            changed += 1
        if changed:
            self._session.commit()
            logger.info("Auto-transición: %d partido(s) a 'en_curso'.", changed)
        return changed

    def register_result(
        self,
        match_id: int,
        home_goals: int,
        away_goals: int,
        official_winner: PredictedWinner | None = None,
    ) -> tuple[Match, list[UserScore]]:
        """
        Registra el resultado oficial de un partido dentro de una única
        transacción atómica:
          1. Valida que home_goals >= 0 y away_goals >= 0.
          2. Actualiza el partido (status, official_home_goals, official_away_goals).
          3. Calcula y persiste los puntos de todos los predictores.

        ``official_winner`` indica quién avanzó cuando el partido se definió
        por penales (eliminatorias). Si es ``None`` se deriva del marcador.

        Raises:
            InvalidScoreError:   si alguno de los goles es negativo.
            MatchNotFoundError:  si no existe ningún partido con ese ID.

        Requirements: 2.4, 2.5, 4.1, 4.7, 8.6, 8.7
        """
        if home_goals < 0 or away_goals < 0:
            raise InvalidScoreError(
                "El marcador debe contener valores numéricos no negativos"
            )

        match = self.get_match(match_id)

        match.official_home_goals = home_goals
        match.official_away_goals = away_goals
        match.official_winner = official_winner
        match.status = MatchStatus.finalizado

        self._session.add(match)

        scoring_svc = ScoringService(self._session)
        scores = scoring_svc.calculate_and_persist_scores(
            match_id, home_goals, away_goals,
            official_winner=official_winner.value if official_winner else None,
        )

        self._session.commit()
        self._session.refresh(match)

        logger.info(
            "Partido %d: resultado registrado %d-%d, estado='finalizado', %d predicciones puntuadas.",
            match_id,
            home_goals,
            away_goals,
            len(scores),
        )
        return match, scores
