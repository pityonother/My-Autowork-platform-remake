@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "APP_NAME=BookingTool"
set "PYTHON=.venv\Scripts\python.exe"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if not exist "%PYTHON%" (
    echo Missing virtual environment python: %PYTHON%
    exit /b 1
)

"%PYTHON%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --name "%APP_NAME%" ^
  --console ^
  --add-data "templates\booking.html;templates" ^
  --add-data "static;static" ^
  --add-data "booking_template_zh.xlsx;." ^
  --hidden-import "uvicorn.logging" ^
  --hidden-import "uvicorn.loops.auto" ^
  --hidden-import "uvicorn.protocols.http.auto" ^
  --hidden-import "uvicorn.protocols.http.h11_impl" ^
  --hidden-import "uvicorn.lifespan.on" ^
  --hidden-import "multipart" ^
  booking_packaged_app.py

if errorlevel 1 exit /b %errorlevel%

set "DIST_DIR=dist\%APP_NAME%"
if not exist "%DIST_DIR%\runtime" mkdir "%DIST_DIR%\runtime"
if exist "runtime\booking_sil_fuca_warehouse_template" robocopy "runtime\booking_sil_fuca_warehouse_template" "%DIST_DIR%\runtime\booking_sil_fuca_warehouse_template" /MIR /NFL /NDL /NJH /NJS >nul

echo.
echo Build finished: %CD%\%DIST_DIR%\%APP_NAME%.exe
endlocal
