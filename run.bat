@echo off
chcp 65001 >nul
title Polla del Mundial 2026

REM ── Ir a la carpeta del proyecto (donde está este .bat) ────────────────
cd /d "%~dp0"

echo.
echo  ===============================
echo   Polla del Mundial 2026
echo  ===============================
echo.

REM ── Verificar que Python existe ────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python no encontrado. Instala Python desde https://python.org
    pause
    exit /b 1
)

REM ── Instalar dependencias si faltan ────────────────────────────────────
echo [1/3] Verificando dependencias...
python -m pip install -r requirements.txt -q --disable-pip-version-check
if errorlevel 1 (
    echo ERROR: No se pudieron instalar las dependencias.
    pause
    exit /b 1
)

REM ── Sembrar partidos si la BD no existe ────────────────────────────────
if not exist world_cup.db (
    echo [2/3] Cargando 72 partidos del Mundial 2026...
    python scripts\seed_2026_matches.py
    if errorlevel 1 (
        echo ERROR: Fallo al cargar los partidos.
        pause
        exit /b 1
    )
) else (
    echo [2/3] Base de datos encontrada.
)

REM ── Abrir el navegador (espera 2 seg para que arranque el servidor) ─────
echo [3/3] Iniciando servidor...
echo.
echo  Abriendo en:  http://127.0.0.1:8000
echo  Para detener: Ctrl+C
echo.
start "" /b cmd /c "timeout /t 2 /nobreak >nul && start http://127.0.0.1:8000"

REM ── Arrancar servidor ──────────────────────────────────────────────────
python -m uvicorn app.main:app --app-dir src --host 127.0.0.1 --port 8000 --reload

echo.
echo Servidor detenido.
pause
