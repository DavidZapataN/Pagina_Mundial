"""Tests de predicciones bonus (campeón/goleador)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401  (registra las tablas)
from app.models import BonusPrediction, Match, TournamentBonus, TournamentPhase, MatchStatus
from app.utils import utcnow
from app.modules.bonus.service import (
    CHAMPION_PTS,
    TOPSCORER_PTS,
    BonusClosedError,
    BonusService,
    compute_bonus_points,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


# ── Función pura de puntuación ────────────────────────────────────────────

def test_compute_ambos_aciertos():
    pred = BonusPrediction(user_id=1, champion="Argentina", top_scorer="Messi")
    official = TournamentBonus(id=1, champion="Argentina", top_scorer="messi")  # case-insensitive
    assert compute_bonus_points(pred, official) == CHAMPION_PTS + TOPSCORER_PTS


def test_compute_acentos_y_espacios_no_importan():
    pred = BonusPrediction(user_id=1, champion="Brasil", top_scorer="  Vinícius  ")
    official = TournamentBonus(id=1, champion="brasil", top_scorer="Vinicius")
    assert compute_bonus_points(pred, official) == CHAMPION_PTS + TOPSCORER_PTS


def test_compute_sin_oficial_da_cero():
    pred = BonusPrediction(user_id=1, champion="Brasil", top_scorer="Neymar")
    assert compute_bonus_points(pred, TournamentBonus(id=1)) == 0


# ── Servicio ──────────────────────────────────────────────────────────────

def _add_match(s, kickoff):
    s.add(Match(home_team="Colombia", away_team="Brasil", kickoff_time=kickoff,
                phase=TournamentPhase.grupos, status=MatchStatus.pendiente))
    s.commit()


def test_is_open_segun_inicio_del_torneo():
    s = _session()
    _add_match(s, utcnow() + timedelta(days=2))
    assert BonusService(s).is_open() is True
    s2 = _session()
    _add_match(s2, utcnow() - timedelta(hours=1))
    assert BonusService(s2).is_open() is False


def test_guardar_y_repuntuar():
    s = _session()
    _add_match(s, utcnow() + timedelta(days=2))
    svc = BonusService(s)
    svc.save_user_bonus(1, "Argentina", "Messi")
    svc.save_user_bonus(2, "Brasil", "Neymar")
    # Antes del resultado oficial no hay puntos.
    assert svc.user_points_map() == {}
    svc.set_official("Argentina", "Messi")
    pts = svc.user_points_map()
    assert pts[1] == CHAMPION_PTS + TOPSCORER_PTS
    assert pts.get(2, 0) == 0


def test_no_se_puede_guardar_cerrado():
    s = _session()
    _add_match(s, utcnow() - timedelta(hours=1))
    with pytest.raises(BonusClosedError):
        BonusService(s).save_user_bonus(1, "Brasil", "Neymar")
