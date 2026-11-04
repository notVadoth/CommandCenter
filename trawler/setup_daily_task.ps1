# CommandCenter: register the trawler as a daily Windows scheduled task (current user, no admin needed).
# Run via setup_daily_task.bat. Re-running it just updates the existing task.
param([string]$At = "6:45am")

$ErrorActionPreference = "Stop"
$taskName = "CommandCenter Trawler"
$runBat   = Join-Path $PSScriptRoot "run_trawler.bat"

$action   = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$runBat`"" -WorkingDirectory $PSScriptRoot
$trigger  = New-ScheduledTaskTrigger -Daily -At $At
# StartWhenAvailable: if the PC was off or asleep at the set time, run as soon as it is back on.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
  -Description "Daily CommandCenter news trawl; writes data\groupings.js for the map." -Force | Out-Null

Write-Host ""
Write-Host "Scheduled task '$taskName' is set to run every day at $At." -ForegroundColor Green
Write-Host "Running it once now so the map has fresh data..."
Start-ScheduledTask -TaskName $taskName
Write-Host "Started. It takes a few minutes; the log is in trawler\logs\last_run.log."
Write-Host "To change the time, run:  setup_daily_task.bat 8:30am"
Write-Host "To remove it, run:        remove_daily_task.bat"
