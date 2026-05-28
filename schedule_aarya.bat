@echo off
title Aarya StockSense Pro — Schedule Background Monitor
cd /d "%~dp0"
color 0A

set SCRIPT=%~dp0monitor.py

REM Find Python
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
    echo  ERROR: Python not found. Run setup.bat first.
    pause & exit /b 1
)

echo.
echo  ============================================================
echo    Aarya StockSense Pro  --  Background Monitor Scheduler
echo    This sets up Windows Task Scheduler to run monitor.py
echo    automatically every day at:
echo      - 09:45 AM  (after US market open)
echo      - 03:45 PM  (before US market close)
echo      - 10:00 AM  (after India market open)
echo    The monitor checks your portfolio + sends email alerts.
echo    No app needs to be open.
echo  ============================================================
echo.

REM Remove old tasks if they exist
schtasks /delete /tn "AaryaMonitor_Morning" /f >nul 2>&1
schtasks /delete /tn "AaryaMonitor_Afternoon" /f >nul 2>&1
schtasks /delete /tn "AaryaMonitor_India" /f >nul 2>&1

REM Create task: US Morning (9:45 AM daily)
schtasks /create /tn "AaryaMonitor_Morning" ^
  /tr "\"%PY%\" \"%SCRIPT%\"" ^
  /sc daily /st 09:45 ^
  /ru "%USERNAME%" ^
  /f >nul
if errorlevel 1 (
    echo  ERROR creating morning task. Try running as Administrator.
    pause & exit /b 1
)

REM Create task: US Afternoon (3:45 PM daily)
schtasks /create /tn "AaryaMonitor_Afternoon" ^
  /tr "\"%PY%\" \"%SCRIPT%\"" ^
  /sc daily /st 15:45 ^
  /ru "%USERNAME%" ^
  /f >nul

REM Create task: India morning run (10:00 AM IST = approximate ET equivalent depends on timezone)
REM If you are in India, change the time below to 10:15 (IST market opens 9:15 AM)
schtasks /create /tn "AaryaMonitor_India" ^
  /tr "\"%PY%\" \"%SCRIPT%\"" ^
  /sc daily /st 10:00 ^
  /ru "%USERNAME%" ^
  /f >nul

echo.
echo  ============================================================
echo    SCHEDULED TASKS CREATED:
echo.
echo    AaryaMonitor_Morning   — 09:45 AM daily
echo    AaryaMonitor_Afternoon — 03:45 PM daily
echo    AaryaMonitor_India     — 10:00 AM daily
echo.
echo    The monitor will:
echo      - Check US + India markets for top 3 buy picks
echo      - Detect penny stock spikes (^>29%% in a day)
echo      - Check your portfolio for sell/stop alerts
echo      - Send you emails automatically
echo.
echo    Logs saved to: %~dp0monitor.log
echo.
echo    To REMOVE the scheduled tasks, run: unschedule_aarya.bat
echo    To RUN MANUALLY NOW:  python monitor.py
echo  ============================================================
echo.
pause
