@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
call ".venv\Scripts\activate.bat"
python -m app.packaging.dev_server reconcile_web_app:app --host 127.0.0.1 --preferred-port 8051
