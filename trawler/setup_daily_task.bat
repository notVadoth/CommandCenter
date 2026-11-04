@echo off
rem Double-click once to make the trawler run automatically every day (default 6:45 am).
rem Optional: pass a different time, e.g.  setup_daily_task.bat 8:30am
set AT=%~1
if "%AT%"=="" set AT=6:45am
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_daily_task.ps1" -At "%AT%"
echo.
pause
