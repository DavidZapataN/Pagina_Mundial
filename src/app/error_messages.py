"""
User-facing error messages in Spanish for Polla del Mundial.

Import and use these strings in HTTP responses and service exceptions so
all copy is defined in one place and easy to translate / update.
"""

ERROR_MESSAGES: dict[str, str] = {
    "username_taken": "Este nombre de usuario ya está en uso",
    "invalid_credentials": "Usuario o contraseña incorrectos",
    "match_closed": "Las predicciones para este partido ya están cerradas",
    "draw_mismatch": "El marcador indica empate; selecciona 'empate' como resultado",
    "invalid_score": "El marcador debe contener valores numéricos no negativos",
    "db_write_failed": "No se pudo guardar la información. Intenta de nuevo.",
}
