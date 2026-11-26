param([Parameter(Mandatory=$true)][string]$Directory,[Parameter(Mandatory=$true)][string]$AcceptedVerificationSha256,
[string]$OutputDirectory,[switch]$ConstructorOnly,[switch]$ConstructChild,[switch]$StartChild,[switch]$ChildTaskMainThread,[switch]$SignalControl,[switch]$SystemPhase2,[switch]$SystemPhase3,[switch]$ParallelAssembly)
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if($ChildTaskMainThread){$StartChild=$true}
if($StartChild){$ConstructChild=$true}
if(-not $OutputDirectory){$OutputDirectory=Join-Path $project ('.boom/vm-entry-images/'+[guid]::NewGuid().ToString('N'))}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
if(-not $installation){throw 'Existing MSVC x64 tools are required'}
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10
$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path -LiteralPath (Join-Path $_.FullName 'um/x64/synchronization.lib')}|Sort-Object Name -Descending|Select-Object -First 1
if(-not $sdk){throw 'Existing Windows SDK import libraries are required'}
$args_=@((Join-Path $PSScriptRoot 'build-vm-entry.py'),'--directory',(Resolve-Path -LiteralPath $Directory).Path,
'--accepted-verification-sha256',$AcceptedVerificationSha256,'--output',[IO.Path]::GetFullPath($OutputDirectory),
'--assembler',(Join-Path $bin 'ml64.exe'),'--linker',(Join-Path $bin 'link.exe'),
'--synchronization',(Join-Path $sdk.FullName 'um/x64/synchronization.lib'),'--kernel32',(Join-Path $sdk.FullName 'um/x64/kernel32.lib'))
if($ConstructorOnly){$args_+='--constructor-only'}
if($ConstructChild){$args_+='--construct-child'}
if($StartChild){$args_+='--start-child'}
if($ChildTaskMainThread){$args_+='--child-task-main-thread'}
if($SignalControl){$args_+='--signal-control'}
if($SystemPhase2){$args_+='--system-phase2'}
if($SystemPhase3){$args_+='--system-phase3'}
if($ParallelAssembly){$args_+='--parallel-assembly'}
& D:/Dev/Python312/python.exe @args_
if($LASTEXITCODE -ne 0){throw 'Assembly-owned VM entry build failed'}
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'verify-vm-entry.py') $OutputDirectory --output (Join-Path $OutputDirectory 'verification.json')
if($LASTEXITCODE -ne 0){throw 'Assembly-owned VM entry independent verification failed'}
Write-Output ([IO.Path]::GetFullPath($OutputDirectory))
