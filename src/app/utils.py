"""
Utilidades compartidas: banderas, grupos y zona horaria de Colombia.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def utcnow() -> datetime:
    """
    UTC actual como datetime *naive* (sin tzinfo).

    Devuelve el mismo valor que el deprecado ``datetime.utcnow()`` pero usando
    una API no deprecada. Se mantiene naive a propósito: todos los datetimes
    guardados en la BD (``kickoff_time``, ``expires_at``, ``created_at``…) son
    naive, así que comparar contra aware lanzaría ``TypeError``.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


_PREDICTION_CUTOFF_MINUTES = 15

# Colombia Time = UTC-5, sin cambio de horario (DST)
_COT = timedelta(hours=-5)

WEEKDAY_ES = {0: "Lun", 1: "Mar", 2: "Mié", 3: "Jue", 4: "Vie", 5: "Sáb", 6: "Dom"}
MONTH_ES = {
    1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic",
}


def to_cot(dt: datetime) -> datetime:
    """Convierte un datetime UTC-naive a Hora de Colombia (UTC-5)."""
    return dt + _COT


def cot_time_str(dt: datetime) -> str:
    """Retorna la hora en formato 12h COT, ej: '2:00 PM'."""
    cot = dt + _COT
    h = cot.hour
    m = cot.minute
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}"


def cot_date(dt: datetime) -> date:
    """Retorna la fecha (date) del partido en hora colombiana."""
    return (dt + _COT).date()


def format_date_header(d: date) -> str:
    """Retorna encabezado de fecha, ej: 'Sáb 13 Jun'."""
    return f"{WEEKDAY_ES[d.weekday()]} {d.day} {MONTH_ES[d.month]}"


# ---------------------------------------------------------------------------
# Banderas por equipo (emoji Unicode)
# ---------------------------------------------------------------------------

TEAM_FLAGS: dict[str, str] = {
    # Grupo A
    "México": "🇲🇽",
    "Sudáfrica": "🇿🇦",
    "Corea del Sur": "🇰🇷",
    "Chequia": "🇨🇿",
    # Grupo B
    "Canadá": "🇨🇦",
    "Bosnia y Herzegovina": "🇧🇦",
    "Catar": "🇶🇦",
    "Suiza": "🇨🇭",
    # Grupo C
    "Brasil": "🇧🇷",
    "Marruecos": "🇲🇦",
    "Escocia": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "Haití": "🇭🇹",
    # Grupo D
    "EE.UU.": "🇺🇸",
    "Paraguay": "🇵🇾",
    "Australia": "🇦🇺",
    "Turquía": "🇹🇷",
    # Grupo E
    "Alemania": "🇩🇪",
    "Curazao": "🇨🇼",
    "Costa de Marfil": "🇨🇮",
    "Ecuador": "🇪🇨",
    # Grupo F
    "Países Bajos": "🇳🇱",
    "Japón": "🇯🇵",
    "Suecia": "🇸🇪",
    "Túnez": "🇹🇳",
    # Grupo G
    "Bélgica": "🇧🇪",
    "Egipto": "🇪🇬",
    "Irán": "🇮🇷",
    "Nueva Zelanda": "🇳🇿",
    # Grupo H
    "España": "🇪🇸",
    "Cabo Verde": "🇨🇻",
    "Arabia Saudí": "🇸🇦",
    "Uruguay": "🇺🇾",
    # Grupo I
    "Francia": "🇫🇷",
    "Senegal": "🇸🇳",
    "Irak": "🇮🇶",
    "Noruega": "🇳🇴",
    # Grupo J
    "Argentina": "🇦🇷",
    "Argelia": "🇩🇿",
    "Austria": "🇦🇹",
    "Jordania": "🇯🇴",
    # Grupo K
    "Portugal": "🇵🇹",
    "RD Congo": "🇨🇩",
    "Uzbekistán": "🇺🇿",
    "Colombia": "🇨🇴",
    # Grupo L
    "Inglaterra": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Croacia": "🇭🇷",
    "Ghana": "🇬🇭",
    "Panamá": "🇵🇦",
}

# Grupos del torneo: letra → lista de equipos
GROUPS: dict[str, list[str]] = {
    "A": ["México", "Sudáfrica", "Corea del Sur", "Chequia"],
    "B": ["Canadá", "Bosnia y Herzegovina", "Catar", "Suiza"],
    "C": ["Brasil", "Marruecos", "Escocia", "Haití"],
    "D": ["EE.UU.", "Paraguay", "Australia", "Turquía"],
    "E": ["Alemania", "Curazao", "Costa de Marfil", "Ecuador"],
    "F": ["Países Bajos", "Japón", "Suecia", "Túnez"],
    "G": ["Bélgica", "Egipto", "Irán", "Nueva Zelanda"],
    "H": ["España", "Cabo Verde", "Arabia Saudí", "Uruguay"],
    "I": ["Francia", "Senegal", "Irak", "Noruega"],
    "J": ["Argentina", "Argelia", "Austria", "Jordania"],
    "K": ["Portugal", "RD Congo", "Uzbekistán", "Colombia"],
    "L": ["Inglaterra", "Croacia", "Ghana", "Panamá"],
}

# Lookup inverso: equipo → letra de grupo
TEAM_GROUP: dict[str, str] = {
    team: letter
    for letter, teams in GROUPS.items()
    for team in teams
}


def get_group(home_team: str, away_team: str) -> str:
    """Retorna la letra del grupo (ej: 'A') o '' si es fase eliminatoria."""
    return TEAM_GROUP.get(home_team) or TEAM_GROUP.get(away_team) or ""


def flag(team: str) -> str:
    """Retorna el emoji de bandera para el equipo dado."""
    return TEAM_FLAGS.get(team, "🏳")


# Códigos ISO 3166-1 alpha-2 para flagcdn.com (minúsculas)
TEAM_ISO: dict[str, str] = {
    "México": "mx", "Sudáfrica": "za", "Corea del Sur": "kr", "Chequia": "cz",
    "Canadá": "ca", "Bosnia y Herzegovina": "ba", "Catar": "qa", "Suiza": "ch",
    "Brasil": "br", "Marruecos": "ma", "Escocia": "gb-sct", "Haití": "ht",
    "EE.UU.": "us", "Paraguay": "py", "Australia": "au", "Turquía": "tr",
    "Alemania": "de", "Curazao": "cw", "Costa de Marfil": "ci", "Ecuador": "ec",
    "Países Bajos": "nl", "Japón": "jp", "Suecia": "se", "Túnez": "tn",
    "Bélgica": "be", "Egipto": "eg", "Irán": "ir", "Nueva Zelanda": "nz",
    "España": "es", "Cabo Verde": "cv", "Arabia Saudí": "sa", "Uruguay": "uy",
    "Francia": "fr", "Senegal": "sn", "Irak": "iq", "Noruega": "no",
    "Argentina": "ar", "Argelia": "dz", "Austria": "at", "Jordania": "jo",
    "Portugal": "pt", "RD Congo": "cd", "Uzbekistán": "uz", "Colombia": "co",
    "Inglaterra": "gb-eng", "Croacia": "hr", "Ghana": "gh", "Panamá": "pa",
}


def flag_url(team: str) -> str:
    """Retorna la URL de imagen de bandera para el equipo (flagcdn.com)."""
    iso = TEAM_ISO.get(team, "")
    if not iso:
        return ""
    return f"https://flagcdn.com/w40/{iso}.png"


# Códigos de 3 letras por equipo
TEAM_CODES: dict[str, str] = {
    "México": "MEX", "Sudáfrica": "RSA", "Corea del Sur": "KOR", "Chequia": "CZE",
    "Canadá": "CAN", "Bosnia y Herzegovina": "BIH", "Catar": "QAT", "Suiza": "SUI",
    "Brasil": "BRA", "Marruecos": "MAR", "Escocia": "SCO", "Haití": "HAI",
    "EE.UU.": "USA", "Paraguay": "PAR", "Australia": "AUS", "Turquía": "TUR",
    "Alemania": "ALE", "Curazao": "CUW", "Costa de Marfil": "CIV", "Ecuador": "ECU",
    "Países Bajos": "NED", "Japón": "JPN", "Suecia": "SUE", "Túnez": "TUN",
    "Bélgica": "BEL", "Egipto": "EGY", "Irán": "IRN", "Nueva Zelanda": "NZL",
    "España": "ESP", "Cabo Verde": "CPV", "Arabia Saudí": "KSA", "Uruguay": "URU",
    "Francia": "FRA", "Senegal": "SEN", "Irak": "IRQ", "Noruega": "NOR",
    "Argentina": "ARG", "Argelia": "ALG", "Austria": "AUT", "Jordania": "JOR",
    "Portugal": "POR", "RD Congo": "COD", "Uzbekistán": "UZB", "Colombia": "COL",
    "Inglaterra": "ENG", "Croacia": "CRO", "Ghana": "GHA", "Panamá": "PAN",
}


def team_code(team: str) -> str:
    """Retorna el código de 3 letras para el equipo dado."""
    return TEAM_CODES.get(team, team[:3].upper())


def is_prediction_open(kickoff_time: datetime) -> bool:
    """True si todavía se puede predecir (más de 15 min antes del partido)."""
    return utcnow() < kickoff_time - timedelta(minutes=_PREDICTION_CUTOFF_MINUTES)
