@echo off
REM =============================================================================
REM HYDRA-UMC-SYNTHETIC-DATA-GEN - run.bat
REM Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
REM GPL-3.0 - see LICENSE
REM =============================================================================
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set VENV_PY=.venv\Scripts\python.exe
) else (
    echo No .venv found - run build.bat first. 1>&2
    exit /b 1
)

"%VENV_PY%" -m hydra_umc_synthetic_data_gen.main %*
set EXIT_CODE=%errorlevel%
pause
exit /b %EXIT_CODE%
