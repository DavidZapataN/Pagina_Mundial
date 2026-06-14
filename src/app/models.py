"""
Data models for Polla del Mundial.

Defines SQLModel table classes and enumerations for all entities:
- Enums: MatchStatus, TournamentPhase, PredictedWinner
- Tables: User, Session, Match, Prediction

Data invariants (enforced at the service layer):
- Prediction.pred_home_goals == pred_away_goals implies predicted_winner == PredictedWinner.draw
- Match.official_home_goals / official_away_goals are NOT NULL only when status == MatchStatus.finalizado
- Prediction.points is NOT NULL only when the associated match has status == MatchStatus.finalizado
- Session.expires_at = last_accessed + 24h; a session is invalid if datetime.utcnow() > expires_at
"""

import secrets
import string
from datetime import datetime, timedelta
from enum import Enum

from sqlmodel import Field, SQLModel, UniqueConstraint

from app.utils import utcnow

# Tras el kickoff, un partido sin resultado se considera "en vivo" solo durante
# esta ventana. Pasado este tiempo deja de mostrarse como en vivo y queda
# "por confirmar" hasta que el updater (o el admin) registre el marcador.
LIVE_WINDOW = timedelta(hours=2, minutes=30)


def _random_code(length: int = 6) -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


# ---------------------------------------------------------------------------
# Enumeraciones / Enums
# ---------------------------------------------------------------------------


class MatchStatus(str, Enum):
    """Estado del ciclo de vida de un partido."""

    pendiente = "pendiente"
    en_curso = "en_curso"
    finalizado = "finalizado"


class TournamentPhase(str, Enum):
    """Fase del torneo a la que pertenece un partido."""

    grupos = "grupos"
    dieciseisavos = "dieciseisavos"   # Round of 32 (new in 2026 with 48 teams)
    octavos = "octavos"
    cuartos = "cuartos"
    semifinal = "semifinal"
    final = "final"


class PredictedWinner(str, Enum):
    """Resultado pronosticado por el usuario para un partido."""

    home = "home"
    away = "away"
    draw = "draw"


# ---------------------------------------------------------------------------
# Tablas SQLModel
# ---------------------------------------------------------------------------


class User(SQLModel, table=True):
    """
    Represents a registered participant in the pool.

    Requirements: 1.1 (registration), 8.1 (persistent storage)
    """

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True, max_length=50)
    password_hash: str
    is_admin: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow)


class Session(SQLModel, table=True):
    """
    Tracks an authenticated user session (24-hour sliding window).

    Requirements: 1.3, 1.6
    Invariant: expires_at = last_accessed + 24h
    """

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    token: str = Field(unique=True, index=True)
    last_accessed: datetime
    expires_at: datetime


class Match(SQLModel, table=True):
    """
    A World Cup match between two teams.

    Requirements: 2.1 (store match data), 2.3 (status transitions), 2.4 (register result)
    Invariants:
    - official_home_goals and official_away_goals are NOT NULL only when status == finalizado
    """

    id: int | None = Field(default=None, primary_key=True)
    home_team: str
    away_team: str
    kickoff_time: datetime
    phase: TournamentPhase
    status: MatchStatus = Field(default=MatchStatus.pendiente)
    official_home_goals: int | None = Field(default=None, ge=0)
    official_away_goals: int | None = Field(default=None, ge=0)
    # Ganador real del partido. En fase de grupos coincide con el marcador,
    # pero en eliminatorias un empate se define por penales: aquí guardamos
    # quién avanzó para puntuar correctamente el acierto de ganador.
    official_winner: PredictedWinner | None = Field(default=None)

    @property
    def is_live(self) -> bool:
        """En curso y dentro de la ventana de juego (para el badge "🔴 En vivo")."""
        if self.status != MatchStatus.en_curso:
            return False
        return utcnow() - self.kickoff_time <= LIVE_WINDOW

    @property
    def awaiting_result(self) -> bool:
        """En curso pero la ventana de juego ya pasó sin resultado registrado."""
        return self.status == MatchStatus.en_curso and not self.is_live


class Prediction(SQLModel, table=True):
    """
    A user's prediction for a specific match (winner + exact scoreline).

    Requirements: 3.2, 3.6 (store predictions), 8.1 (persistence)
    Invariants:
    - pred_home_goals == pred_away_goals implies predicted_winner == PredictedWinner.draw
    - points is NOT NULL only when the associated match has status == finalizado
    - UniqueConstraint on (user_id, match_id): one prediction per user per match
    """

    __table_args__ = (UniqueConstraint("user_id", "match_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    match_id: int = Field(foreign_key="match.id", index=True)
    predicted_winner: PredictedWinner
    pred_home_goals: int = Field(ge=0)
    pred_away_goals: int = Field(ge=0)
    points: int | None = Field(default=None)  # NULL until match is finalizado
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class PoolGroup(SQLModel, table=True):
    """Grupo privado de participantes (familia, amigos, etc.)."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=60)
    join_code: str = Field(unique=True, index=True, max_length=8, default_factory=_random_code)
    creator_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=utcnow)
    start_phase: TournamentPhase | None = Field(default=None)


class UserPoolGroup(SQLModel, table=True):
    """Membresía de un usuario en un grupo privado."""

    __table_args__ = (UniqueConstraint("user_id", "group_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    group_id: int = Field(foreign_key="poolgroup.id", index=True)
    joined_at: datetime = Field(default_factory=utcnow)


class BonusPrediction(SQLModel, table=True):
    """
    Predicción "bonus" de cada usuario para todo el torneo: campeón y goleador.

    Se bloquea cuando arranca el Mundial (primer partido). ``points`` queda en
    NULL hasta que el admin registra los resultados oficiales.
    """

    __table_args__ = (UniqueConstraint("user_id"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True, unique=True)
    champion: str | None = Field(default=None, max_length=60)
    top_scorer: str | None = Field(default=None, max_length=80)
    points: int | None = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class TournamentBonus(SQLModel, table=True):
    """Resultado oficial de los bonus (singleton: siempre id=1)."""

    id: int | None = Field(default=None, primary_key=True)
    champion: str | None = Field(default=None, max_length=60)
    top_scorer: str | None = Field(default=None, max_length=80)
    updated_at: datetime = Field(default_factory=utcnow)
