param([Parameter(Mandatory=$true)][string]$Batch,[Parameter(Mandatory=$true)][string]$Plan,[string]$Family='cds-no-archive-v1',[string]$Output,[string]$FrameOverlay)
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $Output){$Output=Join-Path $project ('.boom/runtime-providers/'+$Family+'/'+[guid]::NewGuid().ToString('N'))}
$root=[IO.Path]::GetFullPath($Output)
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$assembler=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64/ml64.exe"
$assemblerHash=(Get-FileHash -LiteralPath $assembler -Algorithm SHA256).Hash
$prepare=@((Join-Path $PSScriptRoot 'build-runtime-provider-pack.py'),'--batch',$Batch,'--plan',$Plan,'--output',$root,'--family',$Family)
if($FrameOverlay){$prepare+=@('--frame-overlay',(Resolve-Path -LiteralPath $FrameOverlay).Path)}
& D:/Dev/Python312/python.exe @prepare
if($LASTEXITCODE -ne 0){throw 'Provider source generation failed'}
& $assembler /nologo /c "/Fo$root/provider.obj" "$root/provider.asm" > "$root/assembler.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/assembler.log" -Tail 15;throw 'Provider assembly failed'}
if((Get-FileHash -LiteralPath $assembler -Algorithm SHA256).Hash -ne $assemblerHash){throw 'Provider assembler changed during build'}
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'build-runtime-provider-pack.py') --seal --output $root --assembler $assembler
if($LASTEXITCODE -ne 0){throw 'Provider publication failed'}
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'verify-runtime-provider-pack.py') "$root/provider.json" --batch $Batch --plan $Plan --output "$root/verification.json"
if($LASTEXITCODE -ne 0){throw 'Independent runtime provider verification failed'}
Write-Output (Join-Path $root 'provider.json')
