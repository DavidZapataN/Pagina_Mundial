"""
BonusService — predicciones de torneo (campeón y goleador).

Reglas de puntuación:
  - Campeón acertado  → 15 puntos
  - Goleador acertado → 10 puntos

Los bonus se bloquean cuando arranca el Mundial (primer partido) y se
puntúan cuando el administrador registra los resultados oficiales.
"""

from __future__ import annotations

import logging
import unicodedata
from datetime import datetime

from sqlmodel import Session, select

from app.exceptions import PredictionError
from app.models import BonusPrediction, Match, TournamentBonus, TournamentPhase
from app.utils import utcnow

logger = logging.getLogger("polla.bonus")

CHAMPION_PTS = 15
TOPSCORER_PTS = 10


def _norm(value: str | None) -> str:
    """Normaliza para comparar: minúsculas, sin acentos ni espacios extra."""
    if not value:
        return ""
    txt = unicodedata.normalize("NFKD", value)
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return " ".join(txt.lower().split())


def compute_bonus_points(pred: BonusPrediction, official: TournamentBonus) -> int:
    """Función pura: puntos de un bonus dado el resultado oficial."""
    pts = 0
    if official.champion and _norm(pred.champion) == _norm(official.champion):
        pts += CHAMPION_PTS
    if official.top_scorer and _norm(pred.top_scorer) == _norm(official.top_scorer):
        pts += TOPSCORER_PTS
    return pts


class BonusClosedError(PredictionError):
    """Los bonus ya están cerrados (el torneo comenzó)."""


class BonusService:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Estado del torneo
    # ------------------------------------------------------------------

    def tournament_start(self) -> datetime | None:
        """Kickoff del primer partido (None si no hay partidos)."""
        first = self._session.exec(
            select(Match).order_by(Match.kickoff_time)
        ).first()
        return first.kickoff_time if first else None

    def is_open(self, now: datetime | None = None) -> bool:
        """Los bonus están abiertos hasta que arranca el primer partido."""
        start = self.tournament_start()
        if start is None:
            return True
        return (now or utcnow()) < start

    def list_teams(self) -> list[str]:
        """Equipos disponibles (de la fase de grupos), ordenados."""
        rows = self._session.exec(
            select(Match).where(Match.phase == TournamentPhase.grupos)
        ).all()
        teams: set[str] = set()
        for m in rows:
            teams.add(m.home_team)
            teams.add(m.away_team)
        return sorted(teams)

    # ------------------------------------------------------------------
    # Resultado oficial (singleton)
    # ------------------------------------------------------------------

    def get_official(self) -> TournamentBonus:
        official = self._session.get(TournamentBonus, 1)
        if official is None:
            official = TournamentBonus(id=1)
            self._session.add(official)
            self._session.commit()
            self._session.refresh(official)
        return official

    def set_official(self, champion: str | None, top_scorer: str | None) -> int:
        """Registra el resultado oficial y re-puntúa todos los bonus."""
        official = self.get_official()
        official.champion = (champion or "").strip() or None
        official.top_scorer = (top_scorer or "").strip() or None
        official.updated_at = utcnow()
        self._session.add(official)

        preds = self._session.exec(select(BonusPrediction)).all()
        for pred in preds:
            pred.points = compute_bonus_points(pred, official)
            self._session.add(pred)
        self._session.commit()
        logger.info(
            "Bonus oficial actualizado (campeón=%s, goleador=%s); %d bonus re-puntuados.",
            official.champion, official.top_scorer, len(preds),
        )
        return len(preds)

    # ------------------------------------------------------------------
    # Predicción del usuario
    # ------------------------------------------------------------------

    def get_user_bonus(self, user_id: int) -> BonusPrediction | None:
        return self._session.exec(
            select(BonusPrediction).where(BonusPrediction.user_id == user_id)
        ).first()

    def save_user_bonus(
        self, user_id: int, champion: str | None, top_scorer: str | None
    ) -> BonusPrediction:
        if not self.is_open():
            raise BonusClosedError("Los bonus ya están cerrados: el Mundial ya comenzó")

        champion = (champion or "").strip() or None
        top_scorer = (top_scorer or "").strip() or None

        pred = self.get_user_bonus(user_id)
        if pred is None:
            pred = BonusPrediction(user_id=user_id)
        pred.champion = champion
        pred.top_scorer = top_scorer
        pred.updated_at = utcnow()
        self._session.add(pred)
        self._session.commit()
        self._session.refresh(pred)
        return pred

    def user_points_map(self) -> dict[int, int]:
        """user_id → puntos bonus (solo los ya puntuados)."""
        preds = self._session.exec(
            select(BonusPrediction).where(BonusPrediction.points.is_not(None))
        ).all()
        return {p.user_id: (p.points or 0) for p in preds}
