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

logger = logging.getLogger("polla.leaderboard.router")

router = APIRouter()


@router.get("", response_class=HTMLResponse)
async def leaderboard(
    request: Request,
    current_user: User | None = Depends(get_current_user_or_none),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    """
    La tabla de posiciones es siempre por grupo: un usuario solo ve a quienes
    comparten un grupo con él. No existe una tabla global pública (expondría
    los nombres de todos los registrados).

    - No autenticado  → al login.
    - Autenticado     → a sus tablas de grupo.

    Requirements: 5.1, 5.2, 5.3, 5.5
    """
    if current_user is None:
        return RedirectResponse(url="/auth/login", status_code=303)
    return RedirectResponse(url="/groups/mis-tablas", status_code=303)
