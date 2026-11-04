@echo off
rem Stops the daily CommandCenter trawler run.
powershell -NoProfile -Command "Unregister-ScheduledTask -TaskName 'CommandCenter Trawler' -Confirm:$false; Write-Host 'Daily trawler task removed.'"
echo.
pause
