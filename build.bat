@echo off
REM =============================================================================
REM HYDRA-UMC-SYNTHETIC-DATA-GEN - build.bat
REM Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
REM GPL-3.0 - see LICENSE
REM =============================================================================
setlocal
cd /d "%~dp0"

echo == HYDRA-UMC-SYNTHETIC-DATA-GEN :: build ==

echo -- Odometer version bump --
python bump_version.py
if errorlevel 1 ( echo NATIVE VERSION BUMP FAILED. & pause & exit /b 1 )
python "%~dp0bump_manifest_version.py" --sync
if errorlevel 1 ( echo VERSION SYNCHRONIZATION FAILED. & pause & exit /b 1 )
if errorlevel 1 goto :error

echo -- Creating/using virtual environment (.venv) --
if not exist ".venv" (
    python -m venv .venv
    if errorlevel 1 goto :error
)

set VENV_PY=.venv\Scripts\python.exe

echo -- Installing project + dependencies (editable, with dev extras) --
"%VENV_PY%" -m pip install --quiet --upgrade pip
if errorlevel 1 goto :error
"%VENV_PY%" -m pip install --quiet -e ".[dev]"
if errorlevel 1 goto :error

echo -- Compile-check every source file (python -m compileall) --
"%VENV_PY%" -m compileall -q src
if errorlevel 1 goto :error

echo -- Running the real test suite (pytest) --
"%VENV_PY%" -m pytest tests/ -q
if errorlevel 1 goto :error

echo == Build OK ==
pause
exit /b 0

:error
echo == Build FAILED ==
pause
exit /b 1
