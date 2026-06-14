"""
FastAPI router para la tabla de posiciones.

Endpoints:
  GET /leaderboard   — tabla de posiciones completa

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app.database import get_session
from app.models import User
from app.modules.auth.dependencies import get_current_user_or_none
from app.modules.leaderboard.service import LeaderboardService

logger = logging.getLogger("polla.leaderboard.router")

router = APIRouter()


@router.get("", response_class=HTMLResponse)
async def leaderboard(
    request: Request,
    current_user: User | None = Depends(get_current_user_or_none),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """
    Redirige a /groups para usuarios autenticados (tabla por grupo).
    Usuarios no autenticados ven la tabla global.

    Requirements: 5.1, 5.2, 5.3, 5.5
    """
    if current_user is not None:
        return RedirectResponse(url="/groups", status_code=303)

    svc = LeaderboardService(session)
    entries = svc.get_leaderboard()

    from app.templates import render
    return HTMLResponse(render(
        "leaderboard/table.html",
        request=request,
        entries=entries,
        current_user=current_user,
    ))
