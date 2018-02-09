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

# $newTag = New-Object Amazon.EC2.Model.Tag
# $newTag.Key = "drift-status"
# $newTag.Value = "install_splunk"
# New-EC2Tag -Resource $instanceId -Tag $newTag

# Write-Output 'Fetching splunk forwarder'
# $filename = "splunkforwarder-6.4.0-f2c836328108-x64-release.msi"
# Read-S3Object -BucketName directive-tiers.dg-api.com -Key ("ue4-builds/redist/"+$filename) -File ($downloadfolder+"\"+$filename) -Region eu-west-1

# Write-Output 'Installing splunk forwarder'
# Start-Process msiexec.exe -Wait -ArgumentList ("/i "+($downloadfolder+"\"+$filename)+" -qb RECEIVING_INDEXER=`"splunk.devnorth.dg-api.com:9997`" WINEVENTLOG_APP_ENABLE=1 WINEVENTLOG_SEC_ENABLE=1 WINEVENTLOG_SYS_ENABLE=1 WINEVENTLOG_FWD_ENABLE=1 WINEVENTLOG_SET_ENABLE=1 REGISTRYCHECK_U=1 REGISTRYCHECK_BASELINE_U=1 REGISTRYCHECK_LM=1 REGISTRYCHECK_BASELINE_LM=1 WMICHECK_CPUTIME=1 WMICHECK_LOCALDISK=1 WMICHECK_LOCALDISK=1 WMICHECK_FREEDISK=1 WMICHECK_MEMORY=1 AGREETOLICENSE=Yes /L*v "+($setuplogfolder + "\splunk_forwarder_logfile.txt"))

# $splunkinput = "C:\Program Files\SplunkUniversalForwarder\etc\system\local\inputs.conf"
# ac $splunkinput ""
# ac $splunkinput "[monitor://C:\logs\battleserver\...\]"
# ac $splunkinput "sourcetype=battleserver"
# ac $splunkinput ""
# ac $splunkinput "[monitor://C:\logs\drift-serverdaemon\]"
# ac $splunkinput "sourcetype=battleserver-daemon"
# ac $splunkinput ""

$newTag = New-Object Amazon.EC2.Model.Tag
$newTag.Key = "drift-status"
$newTag.Value = "install_directx"
New-EC2Tag -Resource $instanceId -Tag $newTag

Write-Output 'Fetching DirectX setup file'
$filename = "dxwebsetup.exe"
Read-S3Object -BucketName directive-tiers.dg-api.com -Key ("ue4-builds/redist/"+$filename) -File ($downloadfolder+"\"+$filename) -Region eu-west-1

Write-Output 'Installing DirectX'
Start-Process ($downloadfolder+"\"+$filename) -Wait -ArgumentList "/Q"

$newTag = New-Object Amazon.EC2.Model.Tag
$newTag.Key = "drift-status"
$newTag.Value = "install_python"
New-EC2Tag -Resource $instanceId -Tag $newTag

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

$newTag = New-Object Amazon.EC2.Model.Tag
$newTag.Key = "drift-status"
$newTag.Value = "install_visualstudio"
New-EC2Tag -Resource $instanceId -Tag $newTag

Write-Output 'Fetching Visual Studio 2013 Redistribution'
$filename = "vc_redist.x64.vc2013.exe"
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

$newTag = New-Object Amazon.EC2.Model.Tag
$newTag.Key = "drift-status"
$newTag.Value = "install_packages"
New-EC2Tag -Resource $instanceId -Tag $newTag

Write-Output 'Installing python requirements'
Start-Process "c:\python27\scripts\pip.exe" -Wait -ArgumentList ("install -r c:\drift-serverdaemon\requirements.txt")

$newTag = New-Object Amazon.EC2.Model.Tag
$newTag.Key = "drift-status"
$newTag.Value = "install_driftconfig"
New-EC2Tag -Resource $instanceId -Tag $newTag

Write-Output 'Initializing Drift Config'
Start-Process "c:\python27\scripts\driftconfig.exe" -Wait -ArgumentList ("init $domainUrl")


Write-Output 'All Done'
