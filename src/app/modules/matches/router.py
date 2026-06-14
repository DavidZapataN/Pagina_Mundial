"""
FastAPI router para el módulo de partidos.

Endpoints:
  GET  /matches              — lista de partidos (agrupados por fecha o fase)
  GET  /matches/{id}         — detalle de un partido
  POST /matches              — crear un partido (solo admin)
  POST /matches/{id}/result  — registrar resultado oficial (solo admin)
  POST /matches/{id}/status  — actualizar estado (solo admin / scheduler)

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
"""

from __future__ import annotations

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app.database import get_session
from app.error_messages import ERROR_MESSAGES
from app.exceptions import (
    InvalidScoreError,
    MatchError,
    MatchNotFoundError,
    UnauthenticatedError,
)
from app.models import Match, MatchStatus, PredictedWinner, TournamentPhase, User
from app.modules.auth.dependencies import get_current_user_or_none, require_current_user
from app.modules.matches.service import MatchService

logger = logging.getLogger("polla.matches.router")

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_admin(user: User | None) -> User:
    if user is None:
        raise UnauthenticatedError("Se requiere iniciar sesión")
    if not user.is_admin:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Se requieren privilegios de administrador")
    return user


def _error_html(message: str, back_url: str = "/matches") -> str:
    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><title>Error</title>
<style>
body{{font-family:sans-serif;display:flex;flex-direction:column;align-items:center;
  justify-content:center;min-height:100vh;margin:0;background:#003087;color:#FCD116}}
.card{{background:#fff;color:#333;border-radius:8px;padding:2rem 2.5rem;max-width:400px;
  width:90%;text-align:center;box-shadow:0 4px 20px rgba(0,0,0,0.3)}}
.error-msg{{color:#CE1126;font-weight:bold;margin:1rem 0}}
a{{color:#003087;text-decoration:none;font-weight:bold}}
a:hover{{text-decoration:underline}}
</style></head>
<body><div class="card"><h2>Polla del Mundial</h2>
<p class="error-msg">{message}</p>
<p><a href="{back_url}">← Volver</a></p>
</div></body></html>"""


# ---------------------------------------------------------------------------
# GET /matches
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
async def list_matches(
    request: Request,
    filter: str = "upcoming",   # upcoming | past | all
    unpredicted: bool = False,
    current_user: User | None = Depends(get_current_user_or_none),
    session: Session = Depends(get_session),
) -> Response:
    """
    Lista todos los partidos agrupados por fecha COT con filtros.

    Requirements: 2.1, 2.2
    """
    from collections import defaultdict
    from datetime import datetime

    from app.models import Prediction
    from app.utils import cot_date, format_date_header
    from sqlmodel import select as sql_select

    svc = MatchService(session)
    svc.auto_transition_statuses()  # refleja "en vivo" sin esperar al loop
    all_matches = svc.list_matches(group_by="date")

    now = datetime.utcnow()

    # Filtro upcoming / past / all
    if filter == "upcoming":
        matches = [
            m for m in all_matches
            if m.kickoff_time > now or m.status == MatchStatus.en_curso
        ]
    elif filter == "past":
        matches = [
            m for m in all_matches
            if m.kickoff_time <= now and m.status != MatchStatus.en_curso
        ]
    else:
        matches = list(all_matches)

    # Predicciones del usuario autenticado
    user_predictions: dict[int, object] = {}
    if current_user:
        preds = session.exec(
            sql_select(Prediction).where(Prediction.user_id == current_user.id)
        ).all()
        user_predictions = {p.match_id: p for p in preds}

    # Filtro "solo sin predicción"
    if unpredicted and current_user:
        matches = [
            m for m in matches
            if m.id not in user_predictions and m.status == MatchStatus.pendiente
        ]

    # Hero: próximo partido aún abierto + cuántos faltan por predecir
    upcoming_open = sorted(
        [m for m in all_matches if m.status == MatchStatus.pendiente and m.kickoff_time > now],
        key=lambda m: m.kickoff_time,
    )
    next_match = upcoming_open[0] if upcoming_open else None
    pending_count = 0
    if current_user:
        pending_count = sum(1 for m in upcoming_open if m.id not in user_predictions)

    # Agrupar por fecha COT
    grouped: dict[object, list] = defaultdict(list)
    for m in matches:
        grouped[cot_date(m.kickoff_time)].append(m)
    grouped_matches = [
        (format_date_header(d), ms)
        for d, ms in sorted(grouped.items())
    ]

    from app.templates import render
    return HTMLResponse(render(
        "matches/list.html",
        request=request,
        grouped_matches=grouped_matches,
        total_count=len(matches),
        current_user=current_user,
        user_predictions=user_predictions,
        active_filter=filter,
        unpredicted=unpredicted,
        next_match=next_match,
        pending_count=pending_count,
    ))


# ---------------------------------------------------------------------------
# GET /matches/{match_id}
# ---------------------------------------------------------------------------


@router.get("/{match_id}", response_class=HTMLResponse)
async def match_detail(
    request: Request,
    match_id: int,
    current_user: User | None = Depends(get_current_user_or_none),
    session: Session = Depends(get_session),
) -> Response:
    """
    Detalle de un partido (con la predicción del usuario autenticado si existe).

    Requirements: 2.1, 3.7
    """
    svc = MatchService(session)
    try:
        match = svc.get_match(match_id)
    except MatchNotFoundError:
        return HTMLResponse(_error_html("Partido no encontrado", "/matches"), status_code=404)

    prediction = None
    if current_user is not None:
        from app.modules.predictions.service import PredictionService
        from sqlmodel import select
        from app.models import Prediction
        prediction = session.exec(
            select(Prediction).where(
                Prediction.user_id == current_user.id,
                Prediction.match_id == match_id,
            )
        ).first()

    from app.templates import render
    return HTMLResponse(render("matches/detail.html", request=request, match=match,
                                current_user=current_user, prediction=prediction))


# ---------------------------------------------------------------------------
# POST /matches  (admin: create match)
# ---------------------------------------------------------------------------


@router.post("", response_class=HTMLResponse)
async def create_match(
    request: Request,
    home_team: str = Form(...),
    away_team: str = Form(...),
    kickoff_time: str = Form(...),
    phase: TournamentPhase = Form(...),
    current_user: User | None = Depends(get_current_user_or_none),
    session: Session = Depends(get_session),
) -> Response:
    """
    Crea un nuevo partido (solo administradores).

    Requirements: 2.1
    """
    admin = _require_admin(current_user)

    from datetime import datetime
    try:
        kickoff_dt = datetime.fromisoformat(kickoff_time)
    except ValueError:
        return HTMLResponse(
            _error_html("Formato de fecha inválido. Usa YYYY-MM-DDTHH:MM", "/admin"),
            status_code=400,
        )

    match = Match(
        home_team=home_team,
        away_team=away_team,
        kickoff_time=kickoff_dt,
        phase=phase,
        status=MatchStatus.pendiente,
    )
    session.add(match)
    session.commit()
    logger.info("Partido creado por admin %s: %s vs %s", admin.username, home_team, away_team)
    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------------------------------------------------------
# POST /matches/{match_id}/result  (admin: register result)
# ---------------------------------------------------------------------------


@router.post("/{match_id}/result", response_class=HTMLResponse)
async def register_result(
    request: Request,
    match_id: int,
    home_goals: int = Form(...),
    away_goals: int = Form(...),
    advanced: str = Form(""),
    current_user: User | None = Depends(get_current_user_or_none),
    session: Session = Depends(get_session),
) -> Response:
    """
    Registra el resultado oficial de un partido (solo administradores).
    Dispara automáticamente el cálculo de puntuaciones.

    ``advanced`` ("home"/"away") indica quién avanzó cuando una eliminatoria
    quedó empatada y se definió por penales; se ignora si el marcador no es
    empate. Vacío en fase de grupos.

    Requirements: 2.4, 2.5, 4.1, 4.7
    """
    admin = _require_admin(current_user)

    # Solo tiene sentido el "avanzó por penales" si el marcador quedó empatado.
    official_winner: PredictedWinner | None = None
    if home_goals == away_goals and advanced in ("home", "away"):
        official_winner = PredictedWinner(advanced)

    svc = MatchService(session)
    try:
        match, scores = svc.register_result(
            match_id, home_goals, away_goals, official_winner=official_winner
        )
    except InvalidScoreError:
        return HTMLResponse(
            _error_html(ERROR_MESSAGES["invalid_score"], f"/admin"),
            status_code=400,
        )
    except MatchNotFoundError:
        return HTMLResponse(
            _error_html("Partido no encontrado", "/admin"),
            status_code=404,
        )

    logger.info(
        "Resultado registrado por admin %s: partido %d → %d-%d (%d predicciones puntuadas)",
        admin.username, match_id, home_goals, away_goals, len(scores),
    )
    return RedirectResponse(url="/admin", status_code=303)


# ---------------------------------------------------------------------------
# POST /matches/{match_id}/status  (admin / scheduler)
# ---------------------------------------------------------------------------


@router.post("/{match_id}/status", response_class=HTMLResponse)
async def update_match_status(
    request: Request,
    match_id: int,
    new_status: MatchStatus = Form(...),
    current_user: User | None = Depends(get_current_user_or_none),
    session: Session = Depends(get_session),
) -> Response:
    """
    Actualiza el estado de un partido (solo administradores).

    Requirements: 2.3
    """
    _require_admin(current_user)

    svc = MatchService(session)
    try:
        svc.update_status(match_id, new_status)
    except MatchNotFoundError:
        return HTMLResponse(_error_html("Partido no encontrado", "/admin"), status_code=404)

    return RedirectResponse(url="/admin", status_code=303)
