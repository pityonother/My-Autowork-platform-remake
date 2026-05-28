@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

if not "%~1"=="" set "APP_RELEASE_VERSION=%~1"
"%PYTHON%" tools\build_release.py --only modules --output-dir release_site
endlocal
