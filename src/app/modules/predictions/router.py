"""
FastAPI router para el módulo de predicciones.

Endpoints:
  GET  /predictions/me           — historial de predicciones del usuario autenticado
  POST /predictions/{match_id}   — registrar / actualizar predicción

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 6.1, 6.2, 6.3
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlmodel import Session

from app.database import get_session
from app.error_messages import ERROR_MESSAGES
from app.exceptions import DrawMismatchError, MatchClosedError, MatchNotFoundError
from app.models import PredictedWinner, TournamentPhase, User
from app.modules.auth.dependencies import get_current_user_or_none, require_current_user
from app.modules.predictions.service import PredictionService

logger = logging.getLogger("polla.predictions.router")

router = APIRouter()


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
# GET /predictions/me
# ---------------------------------------------------------------------------


@router.get("/me", response_class=HTMLResponse)
async def my_predictions(
    request: Request,
    phase: TournamentPhase | None = None,
    current_user: User = Depends(require_current_user),
    session: Session = Depends(get_session),
) -> Response:
    """
    Historial de predicciones del usuario autenticado.

    Soporta filtrado opcional por fase del torneo vía query param ?phase=...

    Requirements: 3.6, 3.7, 6.1, 6.2, 6.3
    """
    svc = PredictionService(session)
    if phase is not None:
        entries = svc.filter_by_phase(current_user.id, phase)  # type: ignore[arg-type]
    else:
        entries = svc.get_user_predictions(current_user.id)  # type: ignore[arg-type]

    from app.templates import render
    return HTMLResponse(render(
        "predictions/history.html",
        request=request,
        entries=entries,
        current_user=current_user,
        selected_phase=phase,
        phases=list(TournamentPhase),
    ))


# ---------------------------------------------------------------------------
# GET /predictions/reminders  (JSON)
# ---------------------------------------------------------------------------


@router.get("/reminders", response_class=JSONResponse)
async def reminders(
    current_user: User = Depends(require_current_user),
    session: Session = Depends(get_session),
    hours: int = 24,
) -> JSONResponse:
    """
    Partidos próximos (dentro de N horas) que el usuario aún no predijo y
    siguen abiertos. Consumido por el JS de recordatorios.
    """
    from datetime import timedelta

    from sqlmodel import select as sql_select

    from app.models import Match, MatchStatus, Prediction
    from app.utils import is_prediction_open, utcnow

    now = utcnow()
    horizon = now + timedelta(hours=max(1, min(hours, 72)))

    predicted_ids = {
        p.match_id for p in session.exec(
            sql_select(Prediction).where(Prediction.user_id == current_user.id)
        ).all()
    }

    upcoming = session.exec(
        sql_select(Match).where(
            Match.status == MatchStatus.pendiente,
            Match.kickoff_time > now,
            Match.kickoff_time <= horizon,
        ).order_by(Match.kickoff_time)
    ).all()

    items = []
    for m in upcoming:
        if m.id in predicted_ids or not is_prediction_open(m.kickoff_time):
            continue
        items.append({
            "id": m.id,
            "home": m.home_team,
            "away": m.away_team,
            "kickoff": m.kickoff_time.isoformat() + "Z",
            "minutes_left": int((m.kickoff_time - now).total_seconds() // 60),
        })

    return JSONResponse({"count": len(items), "matches": items})


# ---------------------------------------------------------------------------
# POST /predictions/{match_id}
# ---------------------------------------------------------------------------


@router.post("/{match_id}", response_class=HTMLResponse)
async def save_prediction(
    request: Request,
    match_id: int,
    predicted_winner: PredictedWinner = Form(...),
    home_goals: int = Form(...),
    away_goals: int = Form(...),
    current_user: User = Depends(require_current_user),
    session: Session = Depends(get_session),
) -> Response:
    """
    Registra o actualiza la predicción del usuario autenticado para un partido.
    Si el request lleva X-Requested-With: fetch, devuelve JSON en lugar de redirect.

    Requirements: 3.1, 3.2, 3.3, 3.4, 3.6
    """
    is_ajax = request.headers.get("X-Requested-With") == "fetch"
    svc = PredictionService(session)
    try:
        svc.save_prediction(
            user_id=current_user.id,  # type: ignore[arg-type]
            match_id=match_id,
            predicted_winner=predicted_winner,
            home_goals=home_goals,
            away_goals=away_goals,
        )
    except MatchClosedError as exc:
        if is_ajax:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        return HTMLResponse(
            _error_html(ERROR_MESSAGES["match_closed"], f"/matches/{match_id}"),
            status_code=400,
        )
    except DrawMismatchError as exc:
        if is_ajax:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        return HTMLResponse(
            _error_html(ERROR_MESSAGES["draw_mismatch"], f"/matches/{match_id}"),
            status_code=400,
        )
    except MatchNotFoundError:
        if is_ajax:
            return JSONResponse({"ok": False, "error": "Partido no encontrado"}, status_code=404)
        return HTMLResponse(
            _error_html("Partido no encontrado", "/matches"),
            status_code=404,
        )

    logger.info(
        "Predicción guardada: user=%s match=%d %d-%d (%s)",
        current_user.username, match_id, home_goals, away_goals, predicted_winner,
    )
    if is_ajax:
        return JSONResponse({"ok": True})
    return RedirectResponse(url=f"/matches/{match_id}", status_code=303)
