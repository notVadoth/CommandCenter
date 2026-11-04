@echo off
rem CommandCenter: run the news trawler, the headline builder and the market charts once, and keep a log.
rem Windows Task Scheduler runs this every morning (see setup_daily_task.bat); you can also double-click it.
setlocal
cd /d "%~dp0"
if not exist logs mkdir logs

for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set TODAY=%%d
set LOG=logs\trawler_%TODAY%.log

rem Find Python: the "py" launcher first, then "python"
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY (where python >nul 2>nul && set PY=python)
if not defined PY (
  echo [%DATE% %TIME%] Python was not found. Install it from python.org, ticking "Add python.exe to PATH". > logs\last_run.log
  exit /b 1
)

echo [%DATE% %TIME%] starting trawler > "%LOG%"
%PY% trawler.py run >> "%LOG%" 2>&1
set RC=%ERRORLEVEL%
echo. >> "%LOG%"
echo [%DATE% %TIME%] building headline panel >> "%LOG%"
%PY% news.py >> "%LOG%" 2>&1
if errorlevel 1 set RC=%ERRORLEVEL%
echo [%DATE% %TIME%] updating market charts >> "%LOG%"
%PY% markets.py >> "%LOG%" 2>&1
if errorlevel 1 set RC=%ERRORLEVEL%
echo [%DATE% %TIME%] finished with exit code %RC% >> "%LOG%"
copy /y "%LOG%" logs\last_run.log >nul

rem keep 30 days of logs
forfiles /p logs /m trawler_*.log /d -30 /c "cmd /c del @path" >nul 2>nul
exit /b %RC%
