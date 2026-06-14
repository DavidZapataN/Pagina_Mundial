"""
FastAPI router para grupos privados.

Endpoints:
  GET  /groups              — lista de grupos del usuario
  POST /groups/create       — crear grupo
  POST /groups/join         — unirse con código
  GET  /groups/{id}         — tabla de posiciones del grupo
  POST /groups/{id}/phase   — cambiar fase inicial (solo creador)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app.database import get_session
from app.exceptions import AlreadyMemberError, GroupNotFoundError
from app.models import TournamentPhase, User
from app.modules.auth.dependencies import require_current_user
from app.modules.groups.service import GroupService
from app.templates import render

logger = logging.getLogger("polla.groups.router")

router = APIRouter()


@router.get("", response_class=HTMLResponse)
async def groups_list(
    request: Request,
    current_user: User = Depends(require_current_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    svc = GroupService(session)
    groups = svc.get_user_groups(current_user.id)  # type: ignore[arg-type]
    return HTMLResponse(render(
        "groups/list.html",
        request=request,
        current_user=current_user,
        groups=groups,
        phases=list(TournamentPhase),
        error=None,
    ))


@router.post("/create", response_class=HTMLResponse)
async def create_group(
    request: Request,
    name: str = Form(...),
    start_phase: str = Form(default=""),
    current_user: User = Depends(require_current_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    if not name.strip():
        svc = GroupService(session)
        groups = svc.get_user_groups(current_user.id)  # type: ignore[arg-type]
        return HTMLResponse(render(
            "groups/list.html",
            request=request,
            current_user=current_user,
            groups=groups,
            phases=list(TournamentPhase),
            error="El nombre del grupo no puede estar vacío",
        ))

    phase: TournamentPhase | None = None
    if start_phase:
        try:
            phase = TournamentPhase(start_phase)
        except ValueError:
            phase = None

    svc = GroupService(session)
    group = svc.create_group(current_user.id, name, start_phase=phase)  # type: ignore[arg-type]
    return RedirectResponse(url=f"/groups/{group.id}", status_code=303)


@router.post("/join", response_class=HTMLResponse)
async def join_group(
    request: Request,
    join_code: str = Form(...),
    current_user: User = Depends(require_current_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    svc = GroupService(session)
    try:
        group = svc.join_group(current_user.id, join_code)  # type: ignore[arg-type]
        return RedirectResponse(url=f"/groups/{group.id}", status_code=303)
    except (GroupNotFoundError, AlreadyMemberError) as exc:
        groups = svc.get_user_groups(current_user.id)  # type: ignore[arg-type]
        return HTMLResponse(render(
            "groups/list.html",
            request=request,
            current_user=current_user,
            groups=groups,
            phases=list(TournamentPhase),
            error=str(exc),
        ))


@router.get("/mis-tablas", response_class=HTMLResponse)
async def mis_tablas(
    request: Request,
    current_user: User = Depends(require_current_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    svc = GroupService(session)
    groups = svc.get_user_groups(current_user.id)  # type: ignore[arg-type]
    group_data = []
    for info in groups:
        entries = svc.get_group_leaderboard(info.group.id)
        my_position = next(
            (e.position for e in entries if e.user_id == current_user.id), None
        )
        group_data.append({"info": info, "entries": entries, "my_position": my_position})
    return HTMLResponse(render(
        "groups/mis_tablas.html",
        request=request,
        current_user=current_user,
        group_data=group_data,
    ))


@router.get("/{group_id}", response_class=HTMLResponse)
async def group_detail(
    request: Request,
    group_id: int,
    current_user: User = Depends(require_current_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    svc = GroupService(session)
    group = svc.get_group(group_id)
    if group is None or not svc.is_member(current_user.id, group_id):  # type: ignore[arg-type]
        return RedirectResponse(url="/groups", status_code=303)

    entries = svc.get_group_leaderboard(group_id)
    return HTMLResponse(render(
        "groups/detail.html",
        request=request,
        current_user=current_user,
        group=group,
        entries=entries,
        phases=list(TournamentPhase),
        is_creator=group.creator_id == current_user.id,
    ))


@router.post("/{group_id}/phase", response_class=HTMLResponse)
async def set_group_phase(
    request: Request,
    group_id: int,
    start_phase: str = Form(default=""),
    current_user: User = Depends(require_current_user),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    phase: TournamentPhase | None = None
    if start_phase:
        try:
            phase = TournamentPhase(start_phase)
        except ValueError:
            phase = None

    svc = GroupService(session)
    svc.set_start_phase(group_id, current_user.id, phase)  # type: ignore[arg-type]
    return RedirectResponse(url=f"/groups/{group_id}", status_code=303)
