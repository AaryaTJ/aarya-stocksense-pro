@echo off
title Aarya StockSense Pro
cd /d "%~dp0"

echo.
echo  ================================================
echo    Aarya StockSense Pro  --  Starting...
echo  ================================================
echo.

REM ── Find Python ───────────────────────────────────────────────────────
REM Try common install locations, then fall back to PATH
set PY=

if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python310\python.exe" (
    set PY=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python310\python.exe
)
if "%PY%"=="" if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe" (
    set PY=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe
)
if "%PY%"=="" if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe" (
    set PY=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe
)
if "%PY%"=="" (
    where python >nul 2>&1
    if not errorlevel 1 set PY=python
)

if "%PY%"=="" (
    echo  ERROR: Python not found.
    echo  Install Python 3.10+ from https://python.org and re-run.
    pause & exit /b 1
)

set PORT=8502
set URL=http://localhost:%PORT%

echo  Using Python: %PY%
echo  Starting server on %URL%
echo  Browser opens automatically in ~5 seconds.
echo  Press Ctrl+C in this window to stop.
echo.

REM Open browser after delay
start "" /b cmd /c "timeout /t 5 /nobreak >nul & start %URL%"

"%PY%" -m streamlit run app.py --server.headless true --server.port %PORT% ^
  --browser.gatherUsageStats false ^
  --theme.base dark ^
  --theme.primaryColor "#1D9E75" ^
  --theme.backgroundColor "#0F1B2D" ^
  --theme.secondaryBackgroundColor "#0A1628" ^
  --theme.textColor "#C9D6E3"
pause
