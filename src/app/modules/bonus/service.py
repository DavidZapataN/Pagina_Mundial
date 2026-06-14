"""
BonusService — predicciones de torneo (campeón y goleador).

Reglas de puntuación:
  - Campeón acertado  → 15 puntos
  - Goleador acertado → 10 puntos

Los bonus se bloquean cuando arranca el último partido de la fase de
grupos, y se puntúan cuando el administrador registra los resultados
oficiales.
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
    """Los bonus ya están cerrados (terminó la fase de grupos)."""


class BonusService:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Estado del torneo
    # ------------------------------------------------------------------

    def group_stage_end(self) -> datetime | None:
        """Kickoff del último partido de fase de grupos (None si no hay partidos)."""
        last = self._session.exec(
            select(Match)
            .where(Match.phase == TournamentPhase.grupos)
            .order_by(Match.kickoff_time.desc())
        ).first()
        return last.kickoff_time if last else None

    def is_open(self, now: datetime | None = None) -> bool:
        """Los bonus están abiertos hasta que arranca el último partido de grupos."""
        deadline = self.group_stage_end()
        if deadline is None:
            return True
        return (now or utcnow()) < deadline

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
        """
        Resultado oficial (singleton id=1).

        Si aún no existe devuelve un objeto transitorio sin persistir: la fila
        solo se crea cuando el admin guarda un resultado vía ``set_official``.
        Así un simple GET de la página de bonus no escribe en la BD.
        """
        official = self._session.get(TournamentBonus, 1)
        if official is None:
            official = TournamentBonus(id=1)
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
