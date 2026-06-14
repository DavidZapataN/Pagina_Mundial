"""
Unit tests para la puntuación de eliminatorias definidas por penales.

Cuando un partido termina empatado en el marcador pero se define por penales,
el acierto de "ganador" (3 pts) debe basarse en quién avanzó, no en el empate
implícito del marcador.
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


def test_predijo_empate_pero_avanzo_un_equipo_no_da_ganador():
    # Predijo empate puro (0-0); terminó 1-1 (no exacto) y avanzó el visitante.
    pts = score("draw", 0, 0, 1, 1, official_winner=PredictedWinner.away.value)
    assert pts == 0


def test_sin_official_winner_se_deriva_del_marcador():
    # Comportamiento legacy de fase de grupos: el ganador sale del marcador.
    assert score("draw", 0, 0, 2, 2) == 3   # empate acertado, marcador no exacto
    assert score("draw", 2, 2, 2, 2) == 5   # marcador exacto
    assert score("home", 1, 0, 3, 1) == 3   # ganador local correcto
    assert score("away", 1, 0, 3, 1) == 0   # ganador equivocado
