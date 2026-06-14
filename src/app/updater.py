"""
Actualización automática de resultados desde football-data.org.

Expone `update_results()` para uso desde el admin y desde la tarea de fondo.
Requiere la variable de entorno FOOTBALL_API_KEY.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

from sqlmodel import Session, select

from app.database import engine
from app.models import Match, MatchStatus, PredictedWinner
from app.modules.matches.service import MatchService

# Mapeo del campo "winner" de football-data.org → quién avanzó.
# En eliminatorias define correctamente al que pasó por penales.
_WINNER_MAP: dict[str, PredictedWinner] = {
    "HOME_TEAM": PredictedWinner.home,
    "AWAY_TEAM": PredictedWinner.away,
    "DRAW": PredictedWinner.draw,
}


def _scoreline(score: dict) -> tuple[int | None, int | None]:
    """
    Marcador que cuenta para la polla a partir del nodo ``score`` de
    football-data: el resultado de los 90' + alargue, SIN penales.

    Ojo: ``score.fullTime`` incluye los goles de la tanda de penales (un 1-1
    definido por penales aparece como 7-6). Por eso, cuando hay alargue/penales
    usamos ``regularTime`` + ``extraTime``; en partidos normales ``regularTime``
    no viene y usamos ``fullTime``.
    """
    regular = score.get("regularTime") or {}
    if regular.get("home") is not None and regular.get("away") is not None:
        extra = score.get("extraTime") or {}
        home = regular["home"] + (extra.get("home") or 0)
        away = regular["away"] + (extra.get("away") or 0)
        return home, away
    full = score.get("fullTime") or {}
    return full.get("home"), full.get("away")

logger = logging.getLogger("polla.updater")

EN_TO_ES: dict[str, str] = {
    "Mexico": "México", "South Africa": "Sudáfrica", "Korea Republic": "Corea del Sur",
    "Czech Republic": "Chequia", "Czechia": "Chequia", "Canada": "Canadá",
    "Bosnia and Herzegovina": "Bosnia y Herzegovina", "Bosnia-Herzegovina": "Bosnia y Herzegovina",
    "Qatar": "Catar", "Switzerland": "Suiza", "Brazil": "Brasil", "Morocco": "Marruecos",
    "Scotland": "Escocia", "Haiti": "Haití", "USA": "EE.UU.", "United States": "EE.UU.",
    "Paraguay": "Paraguay", "Australia": "Australia", "Turkey": "Turquía", "Türkiye": "Turquía",
    "Germany": "Alemania", "Curaçao": "Curazao", "Curacao": "Curazao",
    "Ivory Coast": "Costa de Marfil", "Côte d'Ivoire": "Costa de Marfil",
    "Ecuador": "Ecuador", "Netherlands": "Países Bajos", "Japan": "Japón",
    "Sweden": "Suecia", "Tunisia": "Túnez", "Belgium": "Bélgica", "Egypt": "Egipto",
    "Iran": "Irán", "New Zealand": "Nueva Zelanda", "Spain": "España",
    "Cape Verde": "Cabo Verde", "Saudi Arabia": "Arabia Saudí", "Uruguay": "Uruguay",
    "France": "Francia", "Senegal": "Senegal", "Iraq": "Irak", "Norway": "Noruega",
    "Argentina": "Argentina", "Algeria": "Argelia", "Austria": "Austria", "Jordan": "Jordania",
    "Portugal": "Portugal", "DR Congo": "RD Congo", "Congo DR": "RD Congo",
    "Democratic Republic of Congo": "RD Congo", "Uzbekistan": "Uzbekistán",
    "Colombia": "Colombia", "England": "Inglaterra", "Croatia": "Croacia",
    "Ghana": "Ghana", "Panama": "Panamá",
}


def update_results() -> dict:
    """
    Consulta football-data.org y registra resultados finalizados.
    Retorna un resumen: {"updated": int, "skipped": int, "error": str|None}
    """
    api_key = os.environ.get("FOOTBALL_API_KEY", "").strip()
    if not api_key:
        return {"updated": 0, "skipped": 0, "error": "FOOTBALL_API_KEY no configurada"}

    try:
        import requests as req
        resp = req.get(
            "https://api.football-data.org/v4/competitions/WC/matches",
            headers={"X-Auth-Token": api_key},
            params={"status": "FINISHED"},
            timeout=15,
        )
        if resp.status_code == 403:
            return {"updated": 0, "skipped": 0, "error": "API key inválida o sin acceso al Mundial"}
        if resp.status_code == 429:
            return {"updated": 0, "skipped": 0, "error": "Límite de solicitudes alcanzado, intenta en un minuto"}
        resp.raise_for_status()
        api_matches = resp.json().get("matches", [])
    except Exception as exc:
        return {"updated": 0, "skipped": 0, "error": str(exc)}

    updated = skipped = 0
    window = timedelta(hours=3)

    with Session(engine) as session:
        svc = MatchService(session)
        for api_m in api_matches:
            home_en = api_m.get("homeTeam", {}).get("name", "")
            away_en = api_m.get("awayTeam", {}).get("name", "")
            score = api_m.get("score", {})
            home_goals, away_goals = _scoreline(score)
            official_winner = _WINNER_MAP.get(score.get("winner") or "")
            utc_str = api_m.get("utcDate", "")

            if not (home_en and away_en and home_goals is not None and away_goals is not None):
                continue

            home_es = EN_TO_ES.get(home_en, home_en)
            away_es = EN_TO_ES.get(away_en, away_en)

            try:
                utc_naive = datetime.fromisoformat(utc_str.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                continue

            matches = session.exec(
                select(Match).where(
                    Match.home_team == home_es,
                    Match.away_team == away_es,
                    Match.kickoff_time >= utc_naive - window,
                    Match.kickoff_time <= utc_naive + window,
                )
            ).all()
            local = matches[0] if matches else None

            if local is None or local.status == MatchStatus.finalizado:
                skipped += 1
                continue

            try:
                svc.register_result(local.id, int(home_goals), int(away_goals), official_winner)
                logger.info("Resultado: %s %d-%d %s", home_es, home_goals, away_goals, away_es)
                updated += 1
            except Exception as exc:
                logger.error("Error registrando %s vs %s: %s", home_es, away_es, exc)

    return {"updated": updated, "skipped": skipped, "error": None}
