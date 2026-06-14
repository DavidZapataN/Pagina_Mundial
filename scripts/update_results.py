"""
Actualización automática de resultados desde football-data.org.

Obtiene los resultados finalizados del Mundial 2026 y los registra
en la base de datos local, calculando los puntos de cada participante.

Uso:
    set FOOTBALL_API_KEY=tu_clave_aqui
    python scripts\\update_results.py

Clave gratuita en: https://www.football-data.org/client/register
Límite del plan gratuito: 10 solicitudes/minuto.

El script es idempotente: si un partido ya tiene resultado en la BD,
no vuelve a procesarlo.
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from datetime import datetime, timezone

try:
    import requests
except ImportError:
    print("ERROR: Falta el paquete 'requests'. Instálalo con:")
    print("  pip install requests")
    sys.exit(1)

from sqlmodel import Session, select

from app.database import create_db_and_tables, engine
from app.models import Match, MatchStatus
from app.modules.matches.service import MatchService

# ---------------------------------------------------------------------------
# Mapeo de nombres en inglés (football-data.org) → español (nuestra BD)
# ---------------------------------------------------------------------------

EN_TO_ES: dict[str, str] = {
    "Mexico": "México",
    "South Africa": "Sudáfrica",
    "Korea Republic": "Corea del Sur",
    "Czech Republic": "Chequia",
    "Czechia": "Chequia",
    "Canada": "Canadá",
    "Bosnia and Herzegovina": "Bosnia y Herzegovina",
    "Bosnia-Herzegovina": "Bosnia y Herzegovina",
    "Qatar": "Catar",
    "Switzerland": "Suiza",
    "Brazil": "Brasil",
    "Morocco": "Marruecos",
    "Scotland": "Escocia",
    "Haiti": "Haití",
    "USA": "EE.UU.",
    "United States": "EE.UU.",
    "Paraguay": "Paraguay",
    "Australia": "Australia",
    "Turkey": "Turquía",
    "Türkiye": "Turquía",
    "Germany": "Alemania",
    "Curaçao": "Curazao",
    "Curacao": "Curazao",
    "Ivory Coast": "Costa de Marfil",
    "Côte d'Ivoire": "Costa de Marfil",
    "Ecuador": "Ecuador",
    "Netherlands": "Países Bajos",
    "Japan": "Japón",
    "Sweden": "Suecia",
    "Tunisia": "Túnez",
    "Belgium": "Bélgica",
    "Egypt": "Egipto",
    "Iran": "Irán",
    "New Zealand": "Nueva Zelanda",
    "Spain": "España",
    "Cape Verde": "Cabo Verde",
    "Saudi Arabia": "Arabia Saudí",
    "Uruguay": "Uruguay",
    "France": "Francia",
    "Senegal": "Senegal",
    "Iraq": "Irak",
    "Norway": "Noruega",
    "Argentina": "Argentina",
    "Algeria": "Argelia",
    "Austria": "Austria",
    "Jordan": "Jordania",
    "Portugal": "Portugal",
    "DR Congo": "RD Congo",
    "Congo DR": "RD Congo",
    "Democratic Republic of Congo": "RD Congo",
    "Uzbekistan": "Uzbekistán",
    "Colombia": "Colombia",
    "England": "Inglaterra",
    "Croatia": "Croacia",
    "Ghana": "Ghana",
    "Panama": "Panamá",
}


def fetch_finished_matches(api_key: str) -> list[dict]:
    """Obtiene partidos finalizados del Mundial 2026 desde la API."""
    url = "https://api.football-data.org/v4/competitions/WC/matches"
    headers = {"X-Auth-Token": api_key}
    params = {"status": "FINISHED"}

    resp = requests.get(url, headers=headers, params=params, timeout=15)

    if resp.status_code == 403:
        print("ERROR: Clave de API inválida o sin acceso al Mundial.")
        print("Regístrate gratis en: https://www.football-data.org/client/register")
        sys.exit(1)

    if resp.status_code == 429:
        print("ERROR: Límite de solicitudes alcanzado. Espera un minuto.")
        sys.exit(1)

    resp.raise_for_status()
    data = resp.json()
    return data.get("matches", [])


def find_local_match(
    session: Session,
    home_es: str,
    away_es: str,
    utc_date: datetime,
) -> Match | None:
    """
    Busca un partido en la BD por equipos y fecha aproximada (±3 horas).
    Usamos ±3h porque el kickoff_time almacenado podría diferir algunos minutos.
    """
    from datetime import timedelta
    window = timedelta(hours=3)
    lo = utc_date - window
    hi = utc_date + window

    results = session.exec(
        select(Match).where(
            Match.home_team == home_es,
            Match.away_team == away_es,
            Match.kickoff_time >= lo,
            Match.kickoff_time <= hi,
        )
    ).all()
    return results[0] if results else None


def update_results() -> None:
    api_key = os.environ.get("FOOTBALL_API_KEY", "").strip()
    if not api_key:
        print("ERROR: Falta la variable de entorno FOOTBALL_API_KEY.")
        print()
        print("Cómo obtener una clave gratuita:")
        print("  1. Ve a https://www.football-data.org/client/register")
        print("  2. Regístrate (es gratis, no necesita tarjeta)")
        print("  3. Copia tu API key del correo de confirmación")
        print()
        print("Luego ejecuta:")
        print("  set FOOTBALL_API_KEY=tu_clave")
        print("  python scripts\\update_results.py")
        sys.exit(1)

    print("Consultando football-data.org...")
    api_matches = fetch_finished_matches(api_key)
    print(f"  {len(api_matches)} partidos finalizados en la API.")

    create_db_and_tables()

    updated = 0
    skipped_already = 0
    not_found = 0

    with Session(engine) as session:
        svc = MatchService(session)

        for api_m in api_matches:
            home_en = api_m.get("homeTeam", {}).get("name", "")
            away_en = api_m.get("awayTeam", {}).get("name", "")
            score = api_m.get("score", {})
            ft = score.get("fullTime", {})
            home_goals = ft.get("home")
            away_goals = ft.get("away")
            utc_str = api_m.get("utcDate", "")

            # Validar que tengamos todo lo necesario
            if not (home_en and away_en and home_goals is not None and away_goals is not None):
                continue

            # Convertir nombres
            home_es = EN_TO_ES.get(home_en, home_en)
            away_es = EN_TO_ES.get(away_en, away_en)

            # Parsear fecha
            try:
                utc_date = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
                utc_naive = utc_date.replace(tzinfo=None)
            except ValueError:
                continue

            # Buscar en nuestra BD
            local_match = find_local_match(session, home_es, away_es, utc_naive)

            if local_match is None:
                not_found += 1
                continue

            if local_match.status == MatchStatus.finalizado:
                skipped_already += 1
                continue

            # Registrar resultado
            try:
                svc.register_result(local_match.id, int(home_goals), int(away_goals))
                print(f"  ✓  {home_es} {int(home_goals)}-{int(away_goals)} {away_es}")
                updated += 1
            except Exception as exc:
                print(f"  ✗  Error en {home_es} vs {away_es}: {exc}")

    print()
    print(f"Resultados actualizados: {updated}")
    print(f"Ya registrados (omitidos): {skipped_already}")
    if not_found:
        print(f"No encontrados en BD: {not_found}  "
              f"(puede que los nombres en inglés no coincidan — revisa EN_TO_ES)")


if __name__ == "__main__":
    update_results()
