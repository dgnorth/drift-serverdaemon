[CmdletBinding()]
Param(
  [Parameter(Mandatory=$True,Position=1)]
  [string]$domainUrl
)

# remember to use: Set-ExecutionPolicy -ExecutionPolicy Unrestricted -Scope CurrentUser

$instanceId = (New-Object System.Net.WebClient).DownloadString("http://169.254.169.254/latest/meta-data/instance-id")

$downloadfolder = "c:\temp\redist"
$setuplogfolder = "c:\logs\setuplogs"

Write-Output 'Creating folders'
New-Item $downloadfolder -itemtype directory
New-Item $setuplogfolder -itemtype directory

Update-Status-Tag -Status "install_directx"

Write-Output 'Fetching DirectX setup file'
$filename = "dxwebsetup.exe"
Read-S3Object -BucketName directive-tiers.dg-api.com -Key ("ue4-builds/redist/"+$filename) -File ($downloadfolder+"\"+$filename) -Region eu-west-1

Write-Output 'Installing DirectX'
Start-Process ($downloadfolder+"\"+$filename) -Wait -ArgumentList "/Q"

Update-Status-Tag -Status "install_python"

Write-Output 'Fetching Python'
$filename = "python-2.7.11.msi"
Read-S3Object -BucketName directive-tiers.dg-api.com -Key ("ue4-builds/redist/"+$filename) -File ($downloadfolder+"\"+$filename) -Region eu-west-1

Write-Output 'Installing Python'
Start-Process msiexec.exe -Wait -ArgumentList ("/i "+($downloadfolder+"\"+$filename)+" -qb WINEVENTLOG_APP_ENABLE=1 WINEVENTLOG_SEC_ENABLE=1 WINEVENTLOG_SYS_ENABLE=1 WINEVENTLOG_FWD_ENABLE=1 WINEVENTLOG_SET_ENABLE=1 REGISTRYCHECK_U=1 REGISTRYCHECK_BASELINE_U=1 REGISTRYCHECK_LM=1 REGISTRYCHECK_BASELINE_LM=1 WMICHECK_CPUTIME=1 WMICHECK_LOCALDISK=1 WMICHECK_LOCALDISK=1 WMICHECK_FREEDISK=1 WMICHECK_MEMORY=1 AGREETOLICENSE=Yes /L*v "+($setuplogfolder + "\" + $filename + ".log"))

$exit_code_sum += $lastexitcode
# add python permanently into path
$env:PATH = ("C:\Python27;C:\Python27\scripts;" + $env:PATH)
$path = [Environment]::GetEnvironmentVariable("Path","Machine")
$path = "c:\python27\;c:\python27\scripts\;"+$path
[Environment]::SetEnvironmentVariable("Path", $path, "Machine")

Update-Status-Tag -Status "install_visualstudio"

Write-Output 'Fetching Visual Studio 2013 Redistribution'
$filename = "vc_redist.x64.vs2013.exe"
Read-S3Object -BucketName directive-tiers.dg-api.com -Key ("ue4-builds/redist/"+$filename) -File ($downloadfolder+"\"+$filename) -Region eu-west-1

Write-Output 'Installing Visual Studio 2103 Redistribution'
Start-Process ($downloadfolder + "\" + $filename) -ArgumentList ("/qn /L*v /silent " + $setuplogfolder + "\" + $filename + ".log") -Wait
$exit_code_sum += $lastexitcode

Write-Output 'Fetching Visual Studio 2015 Redistribution'
$filename = "vc_redist.x64.vs2015.exe"
Read-S3Object -BucketName directive-tiers.dg-api.com -Key ("ue4-builds/redist/"+$filename) -File ($downloadfolder+"\"+$filename) -Region eu-west-1

Write-Output 'Installing Visual Studio 2015 Redistribution'
Start-Process ($downloadfolder + "\" + $filename) -ArgumentList ("/qn /L*v /silent " + $setuplogfolder + "\" + $filename + ".log") -Wait
$exit_code_sum += $lastexitcode

Write-Output 'Fetching Python Visual Studio Extension'
$filename = "VCForPython27.msi"
Read-S3Object -BucketName directive-tiers.dg-api.com -Key ("ue4-builds/redist/"+$filename) -File ($downloadfolder+"\"+$filename) -Region eu-west-1

Write-Output 'Installing Python Visual Studio Extension'
Start-Process msiexec.exe -Wait -ArgumentList ("/i "+($downloadfolder+"\"+$filename)+" -qb WINEVENTLOG_APP_ENABLE=1 WINEVENTLOG_SEC_ENABLE=1 WINEVENTLOG_SYS_ENABLE=1 WINEVENTLOG_FWD_ENABLE=1 WINEVENTLOG_SET_ENABLE=1 REGISTRYCHECK_U=1 REGISTRYCHECK_BASELINE_U=1 REGISTRYCHECK_LM=1 REGISTRYCHECK_BASELINE_LM=1 WMICHECK_CPUTIME=1 WMICHECK_LOCALDISK=1 WMICHECK_LOCALDISK=1 WMICHECK_FREEDISK=1 WMICHECK_MEMORY=1 AGREETOLICENSE=Yes /L*v "+($setuplogfolder + "\" + $filename + ".log"))

$exit_code_sum += $lastexitcode

Write-Output 'Disabling Windows Firewall'
& netsh advfirewall set allprofiles state off

Write-Output 'Installing Telnet client'
& pkgmgr /iu:"TelnetClient"

Update-Status-Tag -Status "install_packages"

Write-Output 'Installing python requirements'
$stdOutLog = "$env:TEMP\stdout.log"
$stdErrLog = "$env:TEMP\stderr.log"
$pipLog = ($setuplogfolder + "\" + "pip.log")
Start-Process "c:\python27\python.exe" -Wait -ArgumentList ("-m pip install --upgrade pip") -RedirectStandardOutput $stdOutLog -RedirectStandardError $stdErrLog
Get-Content $stdOutLog, $stdErrLog | Out-File $pipLog -Append
Start-Process "c:\python27\scripts\pip.exe" -Wait -ArgumentList ("install -r c:\drift-serverdaemon\requirements.txt") -RedirectStandardOutput $stdOutLog -RedirectStandardError $stdErrLog
Get-Content $stdOutLog, $stdErrLog | Out-File $pipLog -Append

Update-Status-Tag -Status "install_driftconfig"

Write-Output 'Initializing Drift Config'
Start-Process "c:\python27\scripts\driftconfig.exe" -Wait -ArgumentList ("init $domainUrl")


Write-Output 'All Done'
