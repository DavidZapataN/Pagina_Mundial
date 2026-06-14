"""
FastAPI application entry point for Polla del Mundial.

Sets up:
- Lifespan handler (DB table creation on startup)
- Static files mount (/static)
- All module routers
- Global exception handlers for domain errors
- Page routes for auth views and admin panel

Requirements: 1.1–1.5, 2.1–2.5, 3.1–3.7, 4.1–4.7, 5.1–5.5, 6.1–6.3, 8.1–8.7
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app.database import create_db_and_tables, get_session
from app.exceptions import (
    AuthError,
    DatabaseError,
    MatchError,
    PredictionError,
    UnauthenticatedError,
)
from app.modules.auth.dependencies import get_current_user_or_none
from app.modules.auth.router import router as auth_router
from app.modules.bonus.router import router as bonus_router
from app.modules.groups.router import router as groups_router
from app.modules.leaderboard.router import router as leaderboard_router
from app.modules.matches.router import router as matches_router
from app.modules.matches.service import MatchService
from app.modules.predictions.router import router as predictions_router
from app.templates import render

logger = logging.getLogger("polla.main")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    create_db_and_tables()
    # Schema migrations for columns added after initial creation
    from sqlalchemy import text
    from app.database import engine
    with engine.connect() as conn:
        for ddl in [
            "ALTER TABLE poolgroup ADD COLUMN IF NOT EXISTS start_phase VARCHAR DEFAULT NULL",
            'ALTER TABLE "match" ADD COLUMN IF NOT EXISTS official_winner VARCHAR DEFAULT NULL',
        ]:
            conn.execute(text(ddl))
        conn.commit()
    from app.seed import seed_if_empty
    seed_if_empty()
    logger.info("Application startup complete.")

    async def _auto_update_loop() -> None:
        while True:
            await asyncio.sleep(300)  # cada 5 minutos
            try:
                from app.database import engine as _engine
                from app.modules.matches.service import MatchService
                with Session(_engine) as _s:
                    MatchService(_s).auto_transition_statuses()
            except Exception as exc:
                logger.error("Auto-transición falló: %s", exc)
            try:
                from app.updater import update_results
                result = update_results()
                if result["updated"]:
                    logger.info("Auto-update: %d resultados actualizados.", result["updated"])
            except Exception as exc:
                logger.error("Auto-update falló: %s", exc)

    task = asyncio.create_task(_auto_update_loop())
    yield
    task.cancel()
    logger.info("Application shutdown.")


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Polla del Mundial",
    description="Juego de predicciones del Mundial de Fútbol para familia y amigos.",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(matches_router, prefix="/matches", tags=["matches"])
app.include_router(predictions_router, prefix="/predictions", tags=["predictions"])
app.include_router(leaderboard_router, prefix="/leaderboard", tags=["leaderboard"])
app.include_router(groups_router, prefix="/groups", tags=["groups"])
app.include_router(bonus_router, prefix="/bonus", tags=["bonus"])

# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(UnauthenticatedError)
async def unauthenticated_handler(request: Request, exc: UnauthenticatedError) -> RedirectResponse:
    return RedirectResponse(url="/auth/login", status_code=303)


@app.exception_handler(AuthError)
async def auth_error_handler(request: Request, exc: AuthError) -> HTMLResponse:
    return HTMLResponse(
        content=f"<h1>Error de autenticación</h1><p>{exc}</p>",
        status_code=401,
    )


@app.exception_handler(MatchError)
@app.exception_handler(PredictionError)
async def domain_error_handler(request: Request, exc: Exception) -> HTMLResponse:
    return HTMLResponse(
        content=f"<h1>Error</h1><p>{exc}</p>",
        status_code=400,
    )


@app.exception_handler(DatabaseError)
async def database_error_handler(request: Request, exc: DatabaseError) -> HTMLResponse:
    logger.error("Database error: %s", exc)
    return HTMLResponse(
        content="<h1>Error de base de datos</h1><p>No se pudo completar la operación. Intenta de nuevo.</p>",
        status_code=503,
    )


# ---------------------------------------------------------------------------
# Page routes (GET — render HTML views)
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def root(current_user=Depends(get_current_user_or_none)) -> RedirectResponse:
    if current_user:
        return RedirectResponse(url="/matches", status_code=303)
    return RedirectResponse(url="/auth/login", status_code=303)


@app.get("/auth/login", response_class=HTMLResponse)
async def login_page(current_user=Depends(get_current_user_or_none), request: Request = None) -> HTMLResponse:
    if current_user:
        return RedirectResponse(url="/matches", status_code=303)
    return HTMLResponse(render("auth/login.html", request=request, current_user=None))


@app.get("/auth/register", response_class=HTMLResponse)
async def register_page(current_user=Depends(get_current_user_or_none), request: Request = None) -> HTMLResponse:
    if current_user:
        return RedirectResponse(url="/matches", status_code=303)
    return HTMLResponse(render("auth/register.html", request=request, current_user=None))


@app.get("/bracket", response_class=HTMLResponse)
async def bracket_view(
    request: Request,
    view: str = "list",
    current_user=Depends(get_current_user_or_none),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    from sqlmodel import select as sql_select
    from app.models import Match, MatchStatus, TournamentPhase
    from app.utils import get_group

    all_matches = session.exec(sql_select(Match).order_by(Match.kickoff_time)).all()

    phase_order = list(TournamentPhase)
    phases_matches: dict[str, list[Match]] = {}
    for m in all_matches:
        key = m.phase.value
        phases_matches.setdefault(key, []).append(m)

    # Group stage standings
    group_standings: dict[str, list[dict]] = {}
    group_matches_map: dict[str, list[Match]] = {}
    for match in phases_matches.get("grupos", []):
        grp = get_group(match.home_team, match.away_team)
        if not grp:
            continue
        group_matches_map.setdefault(grp, []).append(match)
        if match.status != MatchStatus.finalizado:
            continue
        teams = group_standings.setdefault(grp, {})
        hg = match.official_home_goals or 0
        ag = match.official_away_goals or 0
        for team in (match.home_team, match.away_team):
            teams.setdefault(team, {"team": team, "P": 0, "W": 0, "D": 0, "L": 0, "GF": 0, "GA": 0})
        h = teams[match.home_team]
        a = teams[match.away_team]
        h["P"] += 1; a["P"] += 1
        h["GF"] += hg; h["GA"] += ag
        a["GF"] += ag; a["GA"] += hg
        if hg > ag:
            h["W"] += 1; a["L"] += 1
        elif ag > hg:
            a["W"] += 1; h["L"] += 1
        else:
            h["D"] += 1; a["D"] += 1

    sorted_standings: dict[str, list[dict]] = {}
    for grp, teams in sorted(group_standings.items()):
        rows = [
            {**s, "GD": s["GF"] - s["GA"], "Pts": s["W"] * 3 + s["D"]}
            for s in teams.values()
        ]
        rows.sort(key=lambda r: (-r["Pts"], -r["GD"], -r["GF"], r["team"]))
        sorted_standings[grp] = rows

    knockout_phases = [p for p in phase_order if p.value != "grupos"]

    # Visual bracket data
    # Match box: two 36px slots + box-border = ~74px external height, gap = 8px → period = 82px
    # Alignment padding per round: R16=41, QF=123, SF=287 (derived geometrically)
    def pad(lst, n):
        return list(lst)[:n] + [None] * max(0, n - len(lst))

    r32 = phases_matches.get("dieciseisavos", [])
    r16 = phases_matches.get("octavos", [])
    qf  = phases_matches.get("cuartos", [])
    sf  = phases_matches.get("semifinal", [])
    fin = phases_matches.get("final", [])

    left_cols = [
        {"key": "r32", "label": "R32",  "pad": 0,   "gap": 8,   "matches": pad(r32, 8)[:8]},
        {"key": "r16", "label": "R16",  "pad": 41,  "gap": 90,  "matches": pad(r16, 4)[:4]},
        {"key": "qf",  "label": "QF",   "pad": 123, "gap": 254, "matches": pad(qf, 2)[:2]},
        {"key": "sf",  "label": "SF",   "pad": 287, "gap": 0,   "matches": pad(sf[:1], 1)},
    ]
    right_cols = [
        {"key": "sf",  "label": "SF",   "pad": 287, "gap": 0,   "matches": pad(sf[1:2], 1)},
        {"key": "qf",  "label": "QF",   "pad": 123, "gap": 254, "matches": pad(qf[2:4], 2)},
        {"key": "r16", "label": "R16",  "pad": 41,  "gap": 90,  "matches": pad(r16[4:8], 4)},
        {"key": "r32", "label": "R32",  "pad": 0,   "gap": 8,   "matches": pad(r32[8:16], 8)},
    ]

    return HTMLResponse(render(
        "bracket.html",
        request=request,
        current_user=current_user,
        group_matches_map=dict(sorted(group_matches_map.items())),
        group_standings=sorted_standings,
        knockout_phases=knockout_phases,
        phases_matches=phases_matches,
        view=view,
        left_cols=left_cols,
        right_cols=right_cols,
        final_match=fin[0] if fin else None,
    ))


@app.post("/admin/update-results", response_class=JSONResponse)
async def admin_update_results(
    current_user=Depends(get_current_user_or_none),
) -> JSONResponse:
    if not current_user or not current_user.is_admin:
        return JSONResponse({"ok": False, "error": "No autorizado"}, status_code=403)
    from app.updater import update_results
    result = update_results()
    return JSONResponse({"ok": result["error"] is None, **result})


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(
    request: Request,
    current_user=Depends(get_current_user_or_none),
    session: Session = Depends(get_session),
) -> HTMLResponse:
    if not current_user or not current_user.is_admin:
        return RedirectResponse(url="/matches", status_code=303)
    svc = MatchService(session)
    matches = svc.list_matches(group_by="date")
    from app.modules.bonus.service import BonusService
    bonus_svc = BonusService(session)
    return HTMLResponse(render(
        "admin/panel.html",
        request=request,
        current_user=current_user,
        matches=matches,
        bonus_teams=bonus_svc.list_teams(),
        bonus_official=bonus_svc.get_official(),
    ))
