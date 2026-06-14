"""
Router de predicciones bonus (campeón y goleador del torneo).

Endpoints:
  GET  /bonus            — formulario + estado del bonus del usuario
  POST /bonus            — guardar predicción bonus
  POST /bonus/official   — registrar resultado oficial (solo admin)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app.database import get_session
from app.models import User
from app.modules.auth.dependencies import require_current_user
from app.modules.bonus.service import (
    CHAMPION_PTS,
    TOPSCORER_PTS,
    BonusClosedError,
    BonusService,
)

logger = logging.getLogger("polla.bonus.router")

router = APIRouter()


@router.get("", response_class=HTMLResponse)
async def bonus_page(
    request: Request,
    current_user: User = Depends(require_current_user),
    session: Session = Depends(get_session),
    saved: int = 0,
) -> Response:
    svc = BonusService(session)
    from app.templates import render
    return HTMLResponse(render(
        "bonus/predict.html",
        request=request,
        current_user=current_user,
        teams=svc.list_teams(),
        my_bonus=svc.get_user_bonus(current_user.id),
        official=svc.get_official(),
        is_open=svc.is_open(),
        champion_pts=CHAMPION_PTS,
        topscorer_pts=TOPSCORER_PTS,
        saved=bool(saved),
    ))


@router.post("", response_class=HTMLResponse)
async def save_bonus(
    request: Request,
    champion: str = Form(""),
    top_scorer: str = Form(""),
    current_user: User = Depends(require_current_user),
    session: Session = Depends(get_session),
) -> Response:
    svc = BonusService(session)
    try:
        svc.save_user_bonus(current_user.id, champion, top_scorer)
    except BonusClosedError:
        return RedirectResponse(url="/bonus", status_code=303)
    logger.info("Bonus guardado: user=%s campeón=%s goleador=%s",
                current_user.username, champion, top_scorer)
    return RedirectResponse(url="/bonus?saved=1", status_code=303)


@router.post("/official", response_class=HTMLResponse)
async def set_official_bonus(
    request: Request,
    champion: str = Form(""),
    top_scorer: str = Form(""),
    current_user: User = Depends(require_current_user),
    session: Session = Depends(get_session),
) -> Response:
    if not current_user.is_admin:
        return RedirectResponse(url="/matches", status_code=303)
    svc = BonusService(session)
    svc.set_official(champion, top_scorer)
    return RedirectResponse(url="/admin", status_code=303)
