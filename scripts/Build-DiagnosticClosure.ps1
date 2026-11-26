param([Parameter(Mandatory=$true)][string]$Batch,[Parameter(Mandatory=$true)][string]$Plan,[Parameter(Mandatory=$true)][string]$Output,
[string[]]$ClassRoot,[string[]]$Entry,[string]$AdmitProfile,[string]$ReceiverClass,[string]$Runtime='.boom/assembly-runtime-v109-frames-a',[switch]$PreparedSelection,[string[]]$ProviderPack,
[switch]$ParallelAssembly,[ValidateRange(1,8)][int]$AssemblyWorkers=8,[ValidateRange(1,1024)][int]$AssemblyCodeMiB=8)
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$root=[IO.Path]::GetFullPath($Output)
$prepare=@((Join-Path $PSScriptRoot 'prepare-diagnostic-closure.py'),$Batch,'--plan',$Plan,'--output',$root,'--runtime',(Join-Path $runtimePath 'boom-runtime.dll'))
foreach($r in $ClassRoot){$prepare+=@('--class-root',$r)};foreach($r in $Entry){$prepare+=@('--entry',$r)}
foreach($pack in $ProviderPack){$prepare+=@('--provider-pack',(Resolve-Path -LiteralPath $pack).Path)}
if($AdmitProfile){$prepare+=@('--admit-profile',$AdmitProfile)}
if($ReceiverClass){$prepare+=@('--receiver-class',$ReceiverClass)}
[IO.Directory]::CreateDirectory($root)|Out-Null
if($PreparedSelection){
    $artifactRoot=[IO.Path]::GetFullPath((Join-Path $project '.boom'))+[IO.Path]::DirectorySeparatorChar
    if(-not $root.StartsWith($artifactRoot,[StringComparison]::OrdinalIgnoreCase) -or $ClassRoot.Count -or $Entry.Count -or $AdmitProfile -or $ReceiverClass){throw 'Prepared source selection requires its own isolated .boom manifest and no competing roots'}
    if(-not (Test-Path -LiteralPath (Join-Path $root 'closure.json'))){throw 'Prepared source selection is missing'}
}else{
    & D:/Dev/Python312/python.exe @prepare > "$root/prepare.log" 2> "$root/prepare.err"
    if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/prepare.err" -Tail 12;throw 'Diagnostic source selection failed'}
}
$m=Get-Content -LiteralPath "$root/closure.json" -Raw|ConvertFrom-Json|Select-Object objects,exports,selected_runtime_provider_packs,runtime_provider_packs
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe';$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim();$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10;$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path -LiteralPath (Join-Path $_.FullName 'um/x64/synchronization.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$assemblyArgs=@((Join-Path $PSScriptRoot 'diagnostic-objects.py'),'--directory',$root,'--assembler',(Join-Path $bin 'ml64.exe'))
if($ParallelAssembly){$assemblyArgs+=@('--parallel-assembly','--workers',[string]$AssemblyWorkers,'--code-mib',[string]$AssemblyCodeMiB)}
& D:/Dev/Python312/python.exe @assemblyArgs
if($LASTEXITCODE -ne 0){throw 'Diagnostic assembly failed; see the per-unit assembler logs'}
$sealed=Get-Content -LiteralPath (Join-Path $root 'assembly-provenance.json') -Raw|ConvertFrom-Json
$assemblyObjects=@()
if($sealed.schema -eq 1){$assemblyObjects=@($sealed.units|ForEach-Object{$_.object.path})}
elseif($sealed.schema -eq 2){foreach($unit in $sealed.units){foreach($part in $unit.parts){$assemblyObjects+=@($part.object.path)}}}
else{throw 'Unknown diagnostic object provenance schema'}
if(-not $assemblyObjects.Count){throw 'Diagnostic assembler produced no sealed COFF inputs'}
$winsock=$false
foreach($index in $m.selected_runtime_provider_packs){
    $record=$m.runtime_provider_packs[[int]$index].manifest
    if((Get-Item -LiteralPath $record.path).Length -ne $record.digest.size -or (Get-FileHash -LiteralPath $record.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $record.digest.sha256){throw 'Selected provider manifest changed before source image link'}
    $provider=Get-Content -LiteralPath $record.path -Raw|ConvertFrom-Json
    if($provider.family -eq 'normal-native-libraries-v1'){$winsock=$true}
}
$dll=Join-Path $root 'diagnostic-image.dll';$lines=@('/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT','/BREPRO',('/OUT:"'+$dll+'"'))
$lines+=@($assemblyObjects|ForEach-Object{'"'+$_+'"'})
$lines+=@($m.objects|ForEach-Object{'"'+$_+'"'});$lines+=('"'+(Join-Path $runtimePath 'boom-runtime.lib')+'"'),('"'+(Join-Path $sdk.FullName 'um/x64/synchronization.lib')+'"'),('"'+(Join-Path $sdk.FullName 'um/x64/kernel32.lib')+'"');if($winsock){$ws2=Join-Path $sdk.FullName 'um/x64/ws2_32.lib';if(-not (Test-Path -LiteralPath $ws2)){throw 'Selected NativeLibraries requires the same Windows SDK ws2_32.lib'};$lines+=('"'+$ws2+'"')};$lines+=@($m.exports|Sort-Object -Unique|ForEach-Object{'/EXPORT:'+$_})
[IO.File]::WriteAllLines("$root/link.rsp",[string[]]$lines,[Text.UTF8Encoding]::new($false))
& (Join-Path $bin 'link.exe') "@$root/link.rsp" > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/link.log" -Tail 16;throw 'Diagnostic image link failed'}
$verifierRunner=Join-Path $PSScriptRoot 'run-diagnostic-verification.py'
& D:/Dev/Python312/python.exe $verifierRunner $root | Out-Null
if($LASTEXITCODE -ne 0){
    $verifierExit=$LASTEXITCODE
    if(Test-Path -LiteralPath "$root/selection-verification.err"){Get-Content -LiteralPath "$root/selection-verification.err" -Tail 14}
    throw "Diagnostic verification runner exited with $verifierExit. See $root/selection-verification-status.json for the child's exit code and logs. To repeat verification, run D:/Dev/Python312/python.exe `"$verifierRunner`" `"$root`"."
}
Write-Output $dll
