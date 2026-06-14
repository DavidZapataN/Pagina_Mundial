"""
Jinja2 template rendering helper for Polla del Mundial.

Provides a single `render(template_name, **context)` function that
loads templates from src/app/templates/ and returns a rendered string.
"""

from __future__ import annotations

import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.utils import cot_time_str, flag, flag_url, get_group, is_prediction_open, team_code, to_cot

_template_dir = os.path.join(os.path.dirname(__file__), "templates")

_env = Environment(
    loader=FileSystemLoader(_template_dir),
    autoescape=select_autoescape(["html"]),
)

# Registrar filtros personalizados
_env.filters["cot_time"] = cot_time_str   # {{ match.kickoff_time | cot_time }} → "2:00 PM"
_env.filters["cot_dt"] = to_cot           # {{ match.kickoff_time | cot_dt }} → datetime COT
_env.filters["flag"] = flag               # {{ "Colombia" | flag }} → "🇨🇴"
_env.filters["team_code"] = team_code     # {{ "Colombia" | team_code }} → "COL"

# Funciones globales disponibles en todos los templates
_env.globals["get_group"] = get_group                       # get_group(home, away) → "A"
_env.globals["is_prediction_open"] = is_prediction_open    # is_prediction_open(kickoff) → bool
_env.globals["flag_url"] = flag_url                        # flag_url("Colombia") → CDN URL


def render(template_name: str, **context) -> str:
    """Render *template_name* with the given *context* variables."""
    tmpl = _env.get_template(template_name)
    return tmpl.render(**context)
