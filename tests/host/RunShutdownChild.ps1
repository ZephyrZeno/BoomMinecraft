param([Parameter(Mandatory=$true)][string]$Image,[Parameter(Mandatory=$true)][string]$Runtime,[Parameter(Mandatory=$true)][int]$Code)
$ErrorActionPreference='Stop'
Add-Type -Path (Join-Path $PSScriptRoot 'ShutdownProbe.cs')
[BoomShutdownProbe]::HaltInOwnedChild($Image,$Runtime,$Code)
throw 'Native shutdown unexpectedly returned'
