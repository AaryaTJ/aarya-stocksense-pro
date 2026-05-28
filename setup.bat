@echo off
title Aarya StockSense Pro — Setup
cd /d "%~dp0"
color 0A

echo.
echo  ============================================================
echo    Aarya StockSense Pro  --  First-Time Setup
echo    This installs all required packages and creates shortcuts.
echo    Takes about 2-3 minutes on first run.
echo  ============================================================
echo.

REM ── Find Python ───────────────────────────────────────────────────────
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
    echo.
    echo  ERROR: Python not found on this machine.
    echo.
    echo  Please install Python first:
    echo    1. Go to https://python.org/downloads
    echo    2. Download Python 3.10 or newer
    echo    3. During install, check "Add Python to PATH"
    echo    4. Re-run this setup.bat
    echo.
    pause & exit /b 1
)

echo  [OK] Found Python: %PY%
echo.

REM ── Install all required packages ────────────────────────────────────
echo  [1/3] Installing packages (this takes 1-2 minutes)...
"%PY%" -m pip install --upgrade pip --quiet
"%PY%" -m pip install ^
    "streamlit==1.57.0" ^
    yfinance ^
    pandas ^
    numpy ^
    plotly ^
    streamlit-autorefresh ^
    streamlit-lightweight-charts ^
    google-genai ^
    requests ^
    lxml ^
    html5lib ^
    beautifulsoup4 ^
    --quiet

if errorlevel 1 (
    echo.
    echo  ERROR: Package installation failed.
    echo  Check your internet connection and try again.
    pause & exit /b 1
)
echo  [OK] All packages installed.
echo.

REM ── Create aarya_config.json if it doesn't exist ──────────────────────
if not exist "%~dp0aarya_config.json" (
    echo  [2/3] Creating config file...
    (
        echo {
        echo   "alpha_vantage": { "api_key": "" },
        echo   "gemini":        { "api_key": "" },
        echo   "email": {
        echo     "sender_address":      "",
        echo     "sender_app_password": "",
        echo     "alert_recipients":    [],
        echo     "smtp_server":         "smtp.gmail.com",
        echo     "smtp_port":           587
        echo   },
        echo   "zerodha": { "api_key": "", "api_secret": "" }
        echo }
    ) > "%~dp0aarya_config.json"
    echo  [OK] Config file created. Add your API keys via Settings tab.
) else (
    echo  [2/3] Config file already exists — keeping your existing keys.
)
echo.

REM ── Install Start Menu + Desktop shortcuts ────────────────────────────
echo  [3/3] Installing app shortcuts...
powershell -ExecutionPolicy Bypass -File "%~dp0make_shortcut.ps1" >nul 2>&1
if errorlevel 1 (
    echo  WARNING: Could not create shortcuts automatically.
    echo  You can still launch the app by double-clicking run.bat
) else (
    echo  [OK] Shortcuts installed on Desktop and Start Menu.
)
echo.

echo  ============================================================
echo    SETUP COMPLETE!
echo.
echo    TO OPEN THE APP:
echo      Press Windows key, type "Aarya", press Enter
echo      OR double-click "Aarya StockSense Pro" on your Desktop
echo      OR double-click run.bat in this folder
echo.
echo    FIRST TIME? Go to Settings tab in the app and add:
echo      - Your email address (for alerts)
echo      - Gmail App Password (sender account)
echo      - Alpha Vantage API key (free at alphavantage.co)
echo      - Gemini API key (free at aistudio.google.com)
echo.
echo    BACKGROUND MONITORING (optional):
echo      Run schedule_aarya.bat as Administrator to get
echo      automatic daily emails without opening the app.
echo  ============================================================
echo.
pause
