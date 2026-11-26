param([Parameter(Mandatory=$true)][string]$Batch,[Parameter(Mandatory=$true)][string]$Plan,[string]$Output)
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $Output){$Output=Join-Path $project ('.boom/native-frame-overlays/automatic-'+[guid]::NewGuid().ToString('N'))}
$root=[IO.Path]::GetFullPath($Output)
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
$assembler=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64/ml64.exe"
$tool=Join-Path $PSScriptRoot 'native-frame-overlay.py'
& D:/Dev/Python312/python.exe $tool --batch $Batch --plan $Plan --output $root --assembler $assembler
if($LASTEXITCODE -ne 0){throw 'Native frame data generation/assembly failed'}
$manifest=Join-Path $root 'overlay.json'
& D:/Dev/Python312/python.exe $tool --batch $Batch --plan $Plan --verify $manifest
if($LASTEXITCODE -ne 0){throw 'Independent native frame data verification failed'}
Write-Output $manifest
