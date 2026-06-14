"""
FastAPI router for authentication endpoints.

Endpoints:
  POST /register — register a new user (form data)
  POST /login    — authenticate and set session cookie
  POST /logout   — clear session cookie and redirect to login

The prefix `/auth` is applied when this router is included in main.py.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app.database import get_session
from app.error_messages import ERROR_MESSAGES
from app.exceptions import InvalidCredentialsError, UsernameAlreadyExistsError
from app.modules.auth.service import AuthService

logger = logging.getLogger("polla.auth.router")

router = APIRouter()

# ---------------------------------------------------------------------------
# Helper — minimal error HTML page (no template dependency for now)
# ---------------------------------------------------------------------------

def _error_html(message: str, back_url: str = "/") -> str:
    """Return a minimal HTML page displaying an error message in Spanish."""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Error — Polla del Mundial</title>
  <style>
    body {{
      font-family: sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      background: #003087;
      color: #FCD116;
    }}
    .card {{
      background: #fff;
      color: #333;
      border-radius: 8px;
      padding: 2rem 2.5rem;
      max-width: 400px;
      width: 90%;
      text-align: center;
      box-shadow: 0 4px 20px rgba(0,0,0,0.3);
    }}
    .error-msg {{
      color: #CE1126;
      font-weight: bold;
      margin: 1rem 0;
    }}
    a {{
      color: #003087;
      text-decoration: none;
      font-weight: bold;
    }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <div class="card">
    <h2>Polla del Mundial</h2>
    <p class="error-msg">{message}</p>
    <p><a href="{back_url}">← Volver</a></p>
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# POST /register
# ---------------------------------------------------------------------------


@router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    """
    Register a new user.

    On success: redirect to `/`.
    On failure: return 400 with a Spanish error message.

    Requirements: 1.1, 1.2
    """
    svc = AuthService(session)
    try:
        svc.register(username, password)
        logger.info("New user registered via HTTP: %s", username)
        return RedirectResponse(url="/", status_code=303)
    except UsernameAlreadyExistsError:
        logger.warning("Registration failed — username already exists: %s", username)
        return HTMLResponse(
            content=_error_html(
                ERROR_MESSAGES["username_taken"],
                back_url="/auth/register",
            ),
            status_code=400,
        )


# ---------------------------------------------------------------------------
# POST /login
# ---------------------------------------------------------------------------


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: Session = Depends(get_session),
) -> Response:
    """
    Authenticate a user and set an HTTP-only session cookie.

    On success: redirect to `/`.
    On failure: return 400 with a Spanish error message.

    Requirements: 1.3, 1.4
    """
    svc = AuthService(session)
    try:
        token = svc.login(username, password)
        logger.info("User logged in via HTTP: %s", username)
        response = RedirectResponse(url="/", status_code=303)
        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            samesite="lax",
            # secure=False in dev mode — set to True behind HTTPS in production
        )
        return response
    except InvalidCredentialsError:
        logger.warning("Login failed for username: %s", username)
        return HTMLResponse(
            content=_error_html(
                ERROR_MESSAGES["invalid_credentials"],
                back_url="/auth/login",
            ),
            status_code=400,
        )


# ---------------------------------------------------------------------------
# POST /logout
# ---------------------------------------------------------------------------


@router.post("/logout")
async def logout(
    request: Request,
    session: Session = Depends(get_session),
) -> Response:
    """
    Terminate the active session and clear the cookie.

    Redirects to `/auth/login` regardless of whether a cookie was present.

    Requirements: 1.5
    """
    token = request.cookies.get("session_token")
    if token:
        svc = AuthService(session)
        svc.logout(token)
        logger.info("User logged out via HTTP.")

    response = RedirectResponse(url="/auth/login", status_code=303)
    response.delete_cookie(key="session_token")
    return response
