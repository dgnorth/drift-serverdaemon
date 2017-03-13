Write-Output '*** register_basic_tasks STARTING'

$instanceId = (New-Object System.Net.WebClient).DownloadString("http://169.254.169.254/latest/meta-data/instance-id")

# common setup
$driftconfigrepo = "s3://relib-test/directive-games"
$user = "System"
$taskPath = "\Drift\"
$exe = 'c:\python27\python.exe'
$driftconfigexe = "c:\python27\scripts\driftconfig"
$location = "C:\drift-serverdaemon\"
$minuteTrigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration ([System.TimeSpan]::MaxValue)
$dailyTrigger = New-ScheduledTaskTrigger -Daily -At 12am
$startUpTrigger = New-ScheduledTaskTrigger -AtStartup

# Get the latest battleserver builds from S3 every minute and update the local index file
$name = 'Sync builds from S3'
$cmd = "run.py syncbuilds"
Write-Output '*** Registering task '''$name''' with command '''$cmd''''

Unregister-ScheduledTask -TaskName $name -TaskPath $taskPath -Confirm:$false -ErrorAction:SilentlyContinue  
$action = New-ScheduledTaskAction -Execute "$exe" -Argument "$cmd" -WorkingDirectory $location
Register-ScheduledTask -TaskName $name -TaskPath $taskPath -Action $action -Trigger $minuteTrigger -User 'System' | Out-Null

# Update the drift-serverdaemon code every minute if a new version is found
$name = 'Update Server Daemon'
$cmd = "update_daemon.py"
Write-Output '*** Registering task '''$name''' with command '''$cmd''''

Unregister-ScheduledTask -TaskName $name -TaskPath $taskPath -Confirm:$false -ErrorAction:SilentlyContinue  
$action = New-ScheduledTaskAction -Execute "$exe" -Argument "$cmd" -WorkingDirectory $location
Register-ScheduledTask -TaskName $name -TaskPath $taskPath -Action $action -Trigger $minuteTrigger -User 'System' | Out-Null

# Refresh drift config
$name = 'Refresh Drift Config'
$cmd = "pull -i --loop"
Write-Output '*** Registering task '''$name''' with command '''$cmd''''

Unregister-ScheduledTask -TaskName $name -TaskPath $taskPath -Confirm:$false -ErrorAction:SilentlyContinue  
$action = New-ScheduledTaskAction -Execute "$driftconfigexe" -Argument "$cmd" -WorkingDirectory $location
Register-ScheduledTask -TaskName $name -TaskPath $taskPath -Action $action -Trigger $minuteTrigger -User 'System' | Out-Null

# Cleanup builds that are not being referenced by any refs once per day
$name = 'Cleanup old builds'
$cmd = "run.py clean"
Write-Output '*** Registering task '''$name''' with command '''$cmd''''

Unregister-ScheduledTask -TaskName $name -TaskPath $taskPath -Confirm:$false -ErrorAction:SilentlyContinue  
$action = New-ScheduledTaskAction -Execute "$exe" -Argument "$cmd" -WorkingDirectory $location
Register-ScheduledTask -TaskName $name -TaskPath $taskPath -Action $action -Trigger $dailyTrigger -User 'System' | Out-Null

# Cleanup logs and upload to S3 every minute
$name = 'Clean logs and upload to S3'
$cmd = "run.py cleanlogs"
Write-Output '*** Registering task '''$name''' with command '''$cmd''''

Unregister-ScheduledTask -TaskName $name -TaskPath $taskPath -Confirm:$false -ErrorAction:SilentlyContinue  
$action = New-ScheduledTaskAction -Execute "$exe" -Argument "$cmd" -WorkingDirectory $location
Register-ScheduledTask -TaskName $name -TaskPath $taskPath -Action $action -Trigger $minuteTrigger -User 'System' | Out-Null

# Heartbeat all tenants that want to run processes on this machine
$name = 'Heartbeat tenants'
$cmd = "run.py heartbeat"
Write-Output '*** Registering task '''$name''' with command '''$cmd''''

Unregister-ScheduledTask -TaskName $name -TaskPath $taskPath -Confirm:$false -ErrorAction:SilentlyContinue  
$action = New-ScheduledTaskAction -Execute "$exe" -Argument "$cmd" -WorkingDirectory $location
Register-ScheduledTask -TaskName $name -TaskPath $taskPath -Action $action -Trigger $minuteTrigger -User 'System' | Out-Null

# Update our run tasks drift-config every minute
$name = 'Update run tasks'
$cmd = "run.py updateruntasks"
Write-Output '*** Registering task '''$name''' with command '''$cmd''''

Unregister-ScheduledTask -TaskName $name -TaskPath $taskPath -Confirm:$false -ErrorAction:SilentlyContinue  
$action = New-ScheduledTaskAction -Execute "$exe" -Argument "$cmd" -WorkingDirectory $location
Register-ScheduledTask -TaskName $name -TaskPath $taskPath -Action $action -Trigger $minuteTrigger -User 'System' | Out-Null

# Initialize drift config on reboot
$name = 'Initialize Drift Config'
$cmd = "init $driftconfigrepo"
Write-Output '*** Registering task '''$name''' with command '''$cmd''''

Unregister-ScheduledTask -TaskName $name -TaskPath $taskPath -Confirm:$false -ErrorAction:SilentlyContinue  
$action = New-ScheduledTaskAction -Execute "$driftconfigexe" -Argument "$cmd" -WorkingDirectory $location
Register-ScheduledTask -TaskName $name -TaskPath $taskPath -Action $action -Trigger $startUpTrigger -User 'System' | Out-Null

Write-Output '*** register_basic_tasks DONE'