"""
Unit tests para la puntuación de eliminatorias definidas por penales.

Modelo "híbrido": cuando un partido de eliminatoria termina empatado en los
120' y se define por penales, se da el acierto de resultado (+3) tanto a quien
predijo el empate (el resultado real del marcador) como a quien predijo al
equipo que avanzó. Solo queda en 0 quien apostó por el equipo eliminado.
El marcador exacto sigue dando 5.
"""

from __future__ import annotations

from app.models import PredictedWinner
from app.modules.scoring.service import ScoringService

score = ScoringService.score_prediction


def test_marcador_exacto_sigue_dando_5_aunque_haya_penales():
    # Predijo 1-1 exacto; el partido fue 1-1 y se definió por penales.
    pts = score("draw", 1, 1, 1, 1, official_winner=PredictedWinner.home.value)
    assert pts == 5


def test_ganador_por_penales_da_3_aunque_el_marcador_sea_empate():
    # Predijo que ganaba el local (2-1); terminó 1-1 y el local pasó por penales.
    pts = score("home", 2, 1, 1, 1, official_winner=PredictedWinner.home.value)
    assert pts == 3


def test_predijo_empate_y_hubo_empate_da_3_aunque_se_definiera_por_penales():
    # Predijo empate (0-0, no exacto); terminó 1-1 y avanzó el visitante por
    # penales. El resultado de los 120' fue empate → acierta el resultado → 3.
    pts = score("draw", 0, 0, 1, 1, official_winner=PredictedWinner.away.value)
    assert pts == 3


def test_predijo_al_equipo_eliminado_no_da_nada():
    # Terminó 1-1, avanzó el local por penales; predijo que ganaba el visitante.
    pts = score("away", 2, 1, 1, 1, official_winner=PredictedWinner.home.value)
    assert pts == 0


def test_sin_official_winner_se_deriva_del_marcador():
    # Comportamiento legacy de fase de grupos: el ganador sale del marcador.
    assert score("draw", 0, 0, 2, 2) == 3   # empate acertado, marcador no exacto
    assert score("draw", 2, 2, 2, 2) == 5   # marcador exacto
    assert score("home", 1, 0, 3, 1) == 3   # ganador local correcto
    assert score("away", 1, 0, 3, 1) == 0   # ganador equivocado
