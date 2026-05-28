@echo off
title Aarya — Remove Scheduled Tasks
cd /d "%~dp0"
echo Removing Aarya background monitor tasks...
schtasks /delete /tn "AaryaMonitor_Morning"   /f >nul 2>&1
schtasks /delete /tn "AaryaMonitor_Afternoon" /f >nul 2>&1
schtasks /delete /tn "AaryaMonitor_India"     /f >nul 2>&1
echo Done. Background monitoring disabled.
pause
