"""
Sembrado de todos los partidos del Mundial 2026.

Grupos (sorteo del 5 de diciembre de 2024 en Miami):
  A: México, Sudáfrica, Corea del Sur, Chequia
  B: Canadá, Bosnia y Herzegovina, Catar, Suiza
  C: Brasil, Marruecos, Escocia, Haití
  D: EE.UU., Paraguay, Australia, Turquía
  E: Alemania, Curazao, Costa de Marfil, Ecuador
  F: Países Bajos, Japón, Suecia, Túnez
  G: Bélgica, Egipto, Irán, Nueva Zelanda
  H: España, Cabo Verde, Arabia Saudí, Uruguay
  I: Francia, Senegal, Irak, Noruega
  J: Argentina, Argelia, Austria, Jordania
  K: Portugal, RD Congo, Uzbekistán, Colombia
  L: Inglaterra, Croacia, Ghana, Panamá

Uso:
    cd C:/Workspace/Polla_familia
    python scripts/seed_2026_matches.py

El script es idempotente: si los partidos ya existen (mismo home_team +
away_team + kickoff_time), no los duplica.
"""

import sys
import os

# Permite importar `app.*` desde la raíz del proyecto
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from datetime import datetime

from sqlmodel import Session, select

from app.database import create_db_and_tables, engine
from app.models import Match, MatchStatus, TournamentPhase

# ---------------------------------------------------------------------------
# Datos de todos los partidos
# Formato: (home_team, away_team, kickoff_utc, phase)
# Horarios en UTC basados en el calendario oficial (ET = UTC-4, CST = UTC-6)
# Los partidos concurrentes del Jornada 3 comparten el mismo horario.
# ---------------------------------------------------------------------------

MATCHES: list[tuple[str, str, str, str]] = [

    # ════════════════════════════════════════════════════════════════════════
    # GRUPO A — México · Sudáfrica · Corea del Sur · Chequia
    # ════════════════════════════════════════════════════════════════════════
    # Jornada 1
    ("México",         "Sudáfrica",      "2026-06-11 19:00", "grupos"),  # 1pm CST Azteca
    ("Corea del Sur",  "Chequia",         "2026-06-12 01:00", "grupos"),  # 8pm CST Azteca
    # Jornada 2
    ("Chequia",        "Sudáfrica",       "2026-06-18 16:00", "grupos"),  # 12pm ET
    ("México",         "Corea del Sur",   "2026-06-18 23:00", "grupos"),  # 7pm CST
    # Jornada 3 (simultáneos)
    ("Sudáfrica",      "Corea del Sur",   "2026-06-25 01:00", "grupos"),  # 9pm ET Jun 24
    ("Chequia",        "México",          "2026-06-25 01:00", "grupos"),

    # ════════════════════════════════════════════════════════════════════════
    # GRUPO B — Canadá · Bosnia y Herzegovina · Catar · Suiza
    # ════════════════════════════════════════════════════════════════════════
    # Jornada 1
    ("Canadá",              "Bosnia y Herzegovina", "2026-06-12 19:00", "grupos"),  # 3pm ET Toronto
    ("Catar",               "Suiza",                "2026-06-13 19:00", "grupos"),  # 3pm ET
    # Jornada 2
    ("Suiza",               "Bosnia y Herzegovina", "2026-06-18 19:00", "grupos"),  # 3pm ET
    ("Canadá",              "Catar",                "2026-06-18 22:00", "grupos"),  # 6pm ET
    # Jornada 3 (simultáneos)
    ("Suiza",               "Canadá",               "2026-06-24 19:00", "grupos"),  # 3pm ET
    ("Bosnia y Herzegovina","Catar",                "2026-06-24 19:00", "grupos"),

    # ════════════════════════════════════════════════════════════════════════
    # GRUPO C — Brasil · Marruecos · Escocia · Haití
    # ════════════════════════════════════════════════════════════════════════
    # Jornada 1
    ("Brasil",    "Marruecos",  "2026-06-13 22:00", "grupos"),  # 6pm ET
    ("Haití",     "Escocia",    "2026-06-14 01:00", "grupos"),  # 9pm ET Jun 13
    # Jornada 2
    ("Escocia",   "Marruecos",  "2026-06-19 22:00", "grupos"),  # 6pm ET
    ("Brasil",    "Haití",      "2026-06-20 01:00", "grupos"),  # 9pm ET Jun 19
    # Jornada 3 (simultáneos)
    ("Marruecos", "Haití",      "2026-06-24 22:00", "grupos"),  # 6pm ET
    ("Escocia",   "Brasil",     "2026-06-24 22:00", "grupos"),

    # ════════════════════════════════════════════════════════════════════════
    # GRUPO D — EE.UU. · Paraguay · Australia · Turquía
    # ════════════════════════════════════════════════════════════════════════
    # Jornada 1
    ("EE.UU.",    "Paraguay",   "2026-06-12 22:00", "grupos"),  # 6pm ET LA
    ("Australia", "Turquía",    "2026-06-14 04:00", "grupos"),  # 12am ET Jun 14
    # Jornada 2
    ("EE.UU.",    "Australia",  "2026-06-19 19:00", "grupos"),  # 3pm ET Seattle
    ("Turquía",   "Paraguay",   "2026-06-20 04:00", "grupos"),  # 12am ET Jun 20
    # Jornada 3 (simultáneos)
    ("Turquía",   "EE.UU.",     "2026-06-26 01:00", "grupos"),  # 9pm ET Jun 25
    ("Paraguay",  "Australia",  "2026-06-26 01:00", "grupos"),

    # ════════════════════════════════════════════════════════════════════════
    # GRUPO E — Alemania · Curazao · Costa de Marfil · Ecuador
    # ════════════════════════════════════════════════════════════════════════
    # Jornada 1
    ("Alemania",        "Curazao",         "2026-06-14 17:00", "grupos"),  # 1pm ET
    ("Costa de Marfil", "Ecuador",         "2026-06-14 23:00", "grupos"),  # 7pm ET
    # Jornada 2
    ("Alemania",        "Costa de Marfil", "2026-06-20 20:00", "grupos"),  # 4pm ET
    ("Ecuador",         "Curazao",         "2026-06-21 00:00", "grupos"),  # 8pm ET Jun 20
    # Jornada 3 (simultáneos)
    ("Ecuador",         "Alemania",        "2026-06-25 20:00", "grupos"),  # 4pm ET
    ("Curazao",         "Costa de Marfil", "2026-06-25 20:00", "grupos"),

    # ════════════════════════════════════════════════════════════════════════
    # GRUPO F — Países Bajos · Japón · Suecia · Túnez
    # ════════════════════════════════════════════════════════════════════════
    # Jornada 1
    ("Países Bajos", "Japón",          "2026-06-14 20:00", "grupos"),  # 4pm ET
    ("Suecia",       "Túnez",          "2026-06-15 02:00", "grupos"),  # 10pm ET Jun 14
    # Jornada 2
    ("Países Bajos", "Suecia",         "2026-06-20 17:00", "grupos"),  # 1pm ET
    ("Túnez",        "Japón",          "2026-06-21 04:00", "grupos"),  # 12am ET Jun 21
    # Jornada 3 (simultáneos)
    ("Japón",        "Suecia",         "2026-06-25 23:00", "grupos"),  # 7pm ET
    ("Túnez",        "Países Bajos",   "2026-06-25 23:00", "grupos"),

    # ════════════════════════════════════════════════════════════════════════
    # GRUPO G — Bélgica · Egipto · Irán · Nueva Zelanda
    # ════════════════════════════════════════════════════════════════════════
    # Jornada 1
    ("Bélgica",       "Egipto",         "2026-06-15 19:00", "grupos"),  # 3pm ET
    ("Irán",          "Nueva Zelanda",  "2026-06-16 01:00", "grupos"),  # 9pm ET Jun 15
    # Jornada 2
    ("Bélgica",       "Irán",           "2026-06-21 19:00", "grupos"),  # 3pm ET
    ("Egipto",        "Nueva Zelanda",  "2026-06-22 02:00", "grupos"),  # 10pm ET Jun 21
    # Jornada 3 (simultáneos)
    ("Nueva Zelanda", "Bélgica",        "2026-06-27 03:00", "grupos"),  # 11pm ET Jun 26
    ("Egipto",        "Irán",           "2026-06-27 03:00", "grupos"),

    # ════════════════════════════════════════════════════════════════════════
    # GRUPO H — España · Cabo Verde · Arabia Saudí · Uruguay
    # ════════════════════════════════════════════════════════════════════════
    # Jornada 1
    ("España",       "Cabo Verde",    "2026-06-15 16:00", "grupos"),  # 12pm ET
    ("Arabia Saudí", "Uruguay",       "2026-06-15 22:00", "grupos"),  # 6pm ET
    # Jornada 2
    ("España",       "Arabia Saudí",  "2026-06-21 16:00", "grupos"),  # 12pm ET
    ("Uruguay",      "Cabo Verde",    "2026-06-22 00:00", "grupos"),  # 8pm ET Jun 21
    # Jornada 3 (simultáneos)
    ("Uruguay",      "España",        "2026-06-26 23:00", "grupos"),  # 7pm ET
    ("Cabo Verde",   "Arabia Saudí",  "2026-06-26 23:00", "grupos"),

    # ════════════════════════════════════════════════════════════════════════
    # GRUPO I — Francia · Senegal · Irak · Noruega
    # ════════════════════════════════════════════════════════════════════════
    # Jornada 1
    ("Francia",  "Senegal", "2026-06-16 19:00", "grupos"),  # 3pm ET
    ("Irak",     "Noruega", "2026-06-16 22:00", "grupos"),  # 6pm ET
    # Jornada 2
    ("Francia",  "Irak",    "2026-06-22 21:00", "grupos"),  # 5pm ET
    ("Noruega",  "Senegal", "2026-06-23 00:00", "grupos"),  # 8pm ET Jun 22
    # Jornada 3 (simultáneos)
    ("Noruega",  "Francia", "2026-06-26 19:00", "grupos"),  # 3pm ET
    ("Senegal",  "Irak",    "2026-06-26 19:00", "grupos"),

    # ════════════════════════════════════════════════════════════════════════
    # GRUPO J — Argentina · Argelia · Austria · Jordania
    # ════════════════════════════════════════════════════════════════════════
    # Jornada 1
    ("Argentina", "Argelia",  "2026-06-17 01:00", "grupos"),  # 9pm ET Jun 16
    ("Austria",   "Jordania", "2026-06-17 04:00", "grupos"),  # 12am ET Jun 17
    # Jornada 2
    ("Argentina", "Austria",  "2026-06-22 17:00", "grupos"),  # 1pm ET
    ("Jordania",  "Argelia",  "2026-06-23 03:00", "grupos"),  # 11pm ET Jun 22
    # Jornada 3 (simultáneos)
    ("Argelia",   "Austria",  "2026-06-28 02:00", "grupos"),  # 10pm ET Jun 27
    ("Jordania",  "Argentina","2026-06-28 02:00", "grupos"),

    # ════════════════════════════════════════════════════════════════════════
    # GRUPO K — Portugal · RD Congo · Uzbekistán · Colombia
    # ════════════════════════════════════════════════════════════════════════
    # Jornada 1
    ("Portugal",    "RD Congo",   "2026-06-17 17:00", "grupos"),  # 1pm ET
    ("Uzbekistán",  "Colombia",   "2026-06-18 02:00", "grupos"),  # 10pm ET Jun 17
    # Jornada 2
    ("Portugal",    "Uzbekistán", "2026-06-23 17:00", "grupos"),  # 1pm ET
    ("Colombia",    "RD Congo",   "2026-06-24 03:00", "grupos"),  # 11pm ET Jun 23
    # Jornada 3 (simultáneos) — 7:30pm ET
    ("Colombia",    "Portugal",   "2026-06-27 23:30", "grupos"),
    ("RD Congo",    "Uzbekistán", "2026-06-27 23:30", "grupos"),

    # ════════════════════════════════════════════════════════════════════════
    # GRUPO L — Inglaterra · Croacia · Ghana · Panamá
    # ════════════════════════════════════════════════════════════════════════
    # Jornada 1
    ("Inglaterra", "Croacia", "2026-06-17 20:00", "grupos"),  # 4pm ET
    ("Ghana",      "Panamá",  "2026-06-17 23:00", "grupos"),  # 7pm ET
    # Jornada 2
    ("Inglaterra", "Ghana",   "2026-06-23 20:00", "grupos"),  # 4pm ET
    ("Panamá",     "Croacia", "2026-06-24 02:00", "grupos"),  # 10pm ET Jun 23
    # Jornada 3 (simultáneos)
    ("Panamá",     "Inglaterra","2026-06-27 21:00", "grupos"),  # 5pm ET
    ("Croacia",    "Ghana",    "2026-06-27 21:00", "grupos"),
]


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------

def seed() -> None:
    create_db_and_tables()

    with Session(engine) as session:
        existing = {
            (m.home_team, m.away_team, m.kickoff_time)
            for m in session.exec(select(Match)).all()
        }

        inserted = 0
        skipped = 0

        for home, away, kickoff_str, phase_str in MATCHES:
            kickoff_dt = datetime.strptime(kickoff_str, "%Y-%m-%d %H:%M")
            phase = TournamentPhase(phase_str)

            key = (home, away, kickoff_dt)
            if key in existing:
                skipped += 1
                continue

            match = Match(
                home_team=home,
                away_team=away,
                kickoff_time=kickoff_dt,
                phase=phase,
                status=MatchStatus.pendiente,
            )
            session.add(match)
            inserted += 1

        session.commit()

    total = len(MATCHES)
    print(f"\nMundial 2026 sembrado:")
    print(f"  {inserted:3d} partidos insertados")
    print(f"  {skipped:3d} partidos ya existían (omitidos)")
    print(f"  {total:3d} partidos en total (fase de grupos)")
    print()
    print("Grupos:")
    groups = [
        ("A", "México, Sudáfrica, Corea del Sur, Chequia"),
        ("B", "Canadá, Bosnia y Herzegovina, Catar, Suiza"),
        ("C", "Brasil, Marruecos, Escocia, Haití"),
        ("D", "EE.UU., Paraguay, Australia, Turquía"),
        ("E", "Alemania, Curazao, Costa de Marfil, Ecuador"),
        ("F", "Países Bajos, Japón, Suecia, Túnez"),
        ("G", "Bélgica, Egipto, Irán, Nueva Zelanda"),
        ("H", "España, Cabo Verde, Arabia Saudí, Uruguay"),
        ("I", "Francia, Senegal, Irak, Noruega"),
        ("J", "Argentina, Argelia, Austria, Jordania"),
        ("K", "Portugal, RD Congo, Uzbekistán, Colombia"),
        ("L", "Inglaterra, Croacia, Ghana, Panamá"),
    ]
    for letter, teams in groups:
        print(f"  Grupo {letter}: {teams}")

    print()
    print("Próximos pasos:")
    print("  1. Inicia la app: uvicorn app.main:app --app-dir src --reload")
    print("  2. Crea un usuario admin (usuario: 'admin') y entra al panel /admin")
    print("  3. Registra resultados a medida que se juegan los partidos")


if __name__ == "__main__":
    seed()
