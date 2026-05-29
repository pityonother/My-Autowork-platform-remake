@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "APP_NAME=BillClearanceTool"
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
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --add-data "sample_price.xlsx;." ^
  --add-data "booking_template_zh.xlsx;." ^
  --hidden-import "uvicorn.logging" ^
  --hidden-import "uvicorn.loops.auto" ^
  --hidden-import "uvicorn.protocols.http.auto" ^
  --hidden-import "uvicorn.protocols.http.h11_impl" ^
  --hidden-import "uvicorn.lifespan.on" ^
  --hidden-import "multipart" ^
  --hidden-import "pandas" ^
  --hidden-import "PIL.Image" ^
  --hidden-import "PIL.ImageDraw" ^
  --hidden-import "PIL.ImageFont" ^
  --hidden-import "PIL.ImageSequence" ^
  --hidden-import "fitz" ^
  --collect-submodules "openpyxl" ^
  --collect-submodules "xlrd" ^
  --add-data "app\modules\booking\default_warehouse_template;app\modules\booking\default_warehouse_template" ^
  packaged_app.py

if errorlevel 1 exit /b %errorlevel%

set "DIST_DIR=dist\%APP_NAME%"
if /I "%~1"=="--with-runtime" (
    if not exist "%DIST_DIR%\runtime" mkdir "%DIST_DIR%\runtime"
    if exist "runtime\*.db" copy /Y "runtime\*.db" "%DIST_DIR%\runtime\" >nul
    if exist "runtime\ufo_signature" robocopy "runtime\ufo_signature" "%DIST_DIR%\runtime\ufo_signature" /MIR /NFL /NDL /NJH /NJS >nul
    if exist "runtime\booking_sil_fuca_warehouse_template" robocopy "runtime\booking_sil_fuca_warehouse_template" "%DIST_DIR%\runtime\booking_sil_fuca_warehouse_template" /MIR /NFL /NDL /NJH /NJS >nul
    echo Runtime data copied because --with-runtime was explicitly provided.
) else (
    echo Runtime data was NOT copied. Use --with-runtime only for a private local backup build.
)

echo.
echo Build finished: %CD%\%DIST_DIR%\%APP_NAME%.exe
endlocal
