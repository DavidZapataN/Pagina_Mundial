"""
Tests del marcador que el updater extrae del nodo ``score`` de football-data.

El punto clave: en un partido definido por penales ``score.fullTime`` incluye
los goles de la tanda (un 1-1 aparece como 7-6). El marcador que cuenta para la
polla debe ser el de los 120' (regularTime + extraTime), sin penales.
"""

from __future__ import annotations

from app.updater import _scoreline


def test_partido_normal_usa_fulltime():
    score = {"winner": "HOME_TEAM", "fullTime": {"home": 2, "away": 1}}
    assert _scoreline(score) == (2, 1)


def test_penales_no_cuentan_los_goles_de_la_tanda():
    # 1-1 en 120', definido 6-5 por penales. fullTime viene inflado a 7-6.
    score = {
        "winner": "HOME_TEAM",
        "duration": "PENALTY_SHOOTOUT",
        "fullTime": {"home": 7, "away": 6},
        "regularTime": {"home": 1, "away": 1},
        "extraTime": {"home": 0, "away": 0},
        "penalties": {"home": 6, "away": 5},
    }
    assert _scoreline(score) == (1, 1)


def test_definido_en_alargue_suma_regular_mas_extra():
    # 1-1 a los 90', 2-1 tras el alargue (sin penales).
    score = {
        "winner": "HOME_TEAM",
        "duration": "EXTRA_TIME",
        "fullTime": {"home": 2, "away": 1},
        "regularTime": {"home": 1, "away": 1},
        "extraTime": {"home": 1, "away": 0},
    }
    assert _scoreline(score) == (2, 1)


def test_sin_datos_devuelve_none():
    assert _scoreline({}) == (None, None)
