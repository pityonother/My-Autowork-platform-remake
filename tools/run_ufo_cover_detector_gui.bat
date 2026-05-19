@echo off
setlocal
cd /d "%~dp0\.."
".venv\Scripts\python.exe" "tools\ufo_cover_detector_gui.py"
endlocal
