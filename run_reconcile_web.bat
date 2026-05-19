@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
call ".venv\Scripts\activate.bat"
python -m uvicorn reconcile_web_app:app --host 127.0.0.1 --port 8010
