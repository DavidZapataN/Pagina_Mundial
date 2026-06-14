"""
Auto-seed de partidos del Mundial 2026.

Llamado desde el lifespan de la app si la tabla Match está vacía.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlmodel import Session, select

from app.database import engine
from app.models import Match, MatchStatus, TournamentPhase

logger = logging.getLogger("polla.seed")

# (home_team, away_team, kickoff_utc, phase)
MATCHES: list[tuple[str, str, str, str]] = [
    # GRUPO A
    ("México",         "Sudáfrica",             "2026-06-11 19:00", "grupos"),
    ("Corea del Sur",  "Chequia",                "2026-06-12 01:00", "grupos"),
    ("Chequia",        "Sudáfrica",              "2026-06-18 16:00", "grupos"),
    ("México",         "Corea del Sur",          "2026-06-18 23:00", "grupos"),
    ("Sudáfrica",      "Corea del Sur",          "2026-06-25 01:00", "grupos"),
    ("Chequia",        "México",                 "2026-06-25 01:00", "grupos"),
    # GRUPO B
    ("Canadá",              "Bosnia y Herzegovina", "2026-06-12 19:00", "grupos"),
    ("Catar",               "Suiza",                "2026-06-13 19:00", "grupos"),
    ("Suiza",               "Bosnia y Herzegovina", "2026-06-18 19:00", "grupos"),
    ("Canadá",              "Catar",                "2026-06-18 22:00", "grupos"),
    ("Suiza",               "Canadá",               "2026-06-24 19:00", "grupos"),
    ("Bosnia y Herzegovina","Catar",                "2026-06-24 19:00", "grupos"),
    # GRUPO C
    ("Brasil",    "Marruecos",  "2026-06-13 22:00", "grupos"),
    ("Haití",     "Escocia",    "2026-06-14 01:00", "grupos"),
    ("Escocia",   "Marruecos",  "2026-06-19 22:00", "grupos"),
    ("Brasil",    "Haití",      "2026-06-20 01:00", "grupos"),
    ("Marruecos", "Haití",      "2026-06-24 22:00", "grupos"),
    ("Escocia",   "Brasil",     "2026-06-24 22:00", "grupos"),
    # GRUPO D
    ("EE.UU.",    "Paraguay",   "2026-06-12 22:00", "grupos"),
    ("Australia", "Turquía",    "2026-06-14 04:00", "grupos"),
    ("EE.UU.",    "Australia",  "2026-06-19 19:00", "grupos"),
    ("Turquía",   "Paraguay",   "2026-06-20 04:00", "grupos"),
    ("Turquía",   "EE.UU.",     "2026-06-26 01:00", "grupos"),
    ("Paraguay",  "Australia",  "2026-06-26 01:00", "grupos"),
    # GRUPO E
    ("Alemania",        "Curazao",         "2026-06-14 17:00", "grupos"),
    ("Costa de Marfil", "Ecuador",         "2026-06-14 23:00", "grupos"),
    ("Alemania",        "Costa de Marfil", "2026-06-20 20:00", "grupos"),
    ("Ecuador",         "Curazao",         "2026-06-21 00:00", "grupos"),
    ("Ecuador",         "Alemania",        "2026-06-25 20:00", "grupos"),
    ("Curazao",         "Costa de Marfil", "2026-06-25 20:00", "grupos"),
    # GRUPO F
    ("Países Bajos", "Japón",          "2026-06-14 20:00", "grupos"),
    ("Suecia",       "Túnez",          "2026-06-15 02:00", "grupos"),
    ("Países Bajos", "Suecia",         "2026-06-20 17:00", "grupos"),
    ("Túnez",        "Japón",          "2026-06-21 04:00", "grupos"),
    ("Japón",        "Suecia",         "2026-06-25 23:00", "grupos"),
    ("Túnez",        "Países Bajos",   "2026-06-25 23:00", "grupos"),
    # GRUPO G
    ("Bélgica",       "Egipto",         "2026-06-15 19:00", "grupos"),
    ("Irán",          "Nueva Zelanda",  "2026-06-16 01:00", "grupos"),
    ("Bélgica",       "Irán",           "2026-06-21 19:00", "grupos"),
    ("Egipto",        "Nueva Zelanda",  "2026-06-22 02:00", "grupos"),
    ("Nueva Zelanda", "Bélgica",        "2026-06-27 03:00", "grupos"),
    ("Egipto",        "Irán",           "2026-06-27 03:00", "grupos"),
    # GRUPO H
    ("España",       "Cabo Verde",    "2026-06-15 16:00", "grupos"),
    ("Arabia Saudí", "Uruguay",       "2026-06-15 22:00", "grupos"),
    ("España",       "Arabia Saudí",  "2026-06-21 16:00", "grupos"),
    ("Uruguay",      "Cabo Verde",    "2026-06-22 00:00", "grupos"),
    ("Uruguay",      "España",        "2026-06-26 23:00", "grupos"),
    ("Cabo Verde",   "Arabia Saudí",  "2026-06-26 23:00", "grupos"),
    # GRUPO I
    ("Francia",  "Senegal", "2026-06-16 19:00", "grupos"),
    ("Irak",     "Noruega", "2026-06-16 22:00", "grupos"),
    ("Francia",  "Irak",    "2026-06-22 21:00", "grupos"),
    ("Noruega",  "Senegal", "2026-06-23 00:00", "grupos"),
    ("Noruega",  "Francia", "2026-06-26 19:00", "grupos"),
    ("Senegal",  "Irak",    "2026-06-26 19:00", "grupos"),
    # GRUPO J
    ("Argentina", "Argelia",   "2026-06-17 01:00", "grupos"),
    ("Austria",   "Jordania",  "2026-06-17 04:00", "grupos"),
    ("Argentina", "Austria",   "2026-06-22 17:00", "grupos"),
    ("Jordania",  "Argelia",   "2026-06-23 03:00", "grupos"),
    ("Argelia",   "Austria",   "2026-06-28 02:00", "grupos"),
    ("Jordania",  "Argentina", "2026-06-28 02:00", "grupos"),
    # GRUPO K
    ("Portugal",    "RD Congo",   "2026-06-17 17:00", "grupos"),
    ("Uzbekistán",  "Colombia",   "2026-06-18 02:00", "grupos"),
    ("Portugal",    "Uzbekistán", "2026-06-23 17:00", "grupos"),
    ("Colombia",    "RD Congo",   "2026-06-24 03:00", "grupos"),
    ("Colombia",    "Portugal",   "2026-06-27 23:30", "grupos"),
    ("RD Congo",    "Uzbekistán", "2026-06-27 23:30", "grupos"),
    # GRUPO L
    ("Inglaterra", "Croacia",   "2026-06-17 20:00", "grupos"),
    ("Ghana",      "Panamá",    "2026-06-17 23:00", "grupos"),
    ("Inglaterra", "Ghana",     "2026-06-23 20:00", "grupos"),
    ("Panamá",     "Croacia",   "2026-06-24 02:00", "grupos"),
    ("Panamá",     "Inglaterra","2026-06-27 21:00", "grupos"),
    ("Croacia",    "Ghana",     "2026-06-27 21:00", "grupos"),
]


def seed_if_empty() -> None:
    with Session(engine) as session:
        if session.exec(select(Match)).first() is not None:
            return  # ya hay datos, no hacer nada

        existing = set()
        inserted = 0
        for home, away, kickoff_str, phase_str in MATCHES:
            kickoff_dt = datetime.strptime(kickoff_str, "%Y-%m-%d %H:%M")
            key = (home, away, kickoff_dt)
            if key in existing:
                continue
            existing.add(key)
            session.add(Match(
                home_team=home,
                away_team=away,
                kickoff_time=kickoff_dt,
                phase=TournamentPhase(phase_str),
                status=MatchStatus.pendiente,
            ))
            inserted += 1

        session.commit()
        logger.info("Seed completado: %d partidos insertados.", inserted)
