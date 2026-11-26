param([string]$Boom='target/release/boom.exe')
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$compiler=(Resolve-Path -LiteralPath $Boom).Path
$root=Join-Path $project ('.boom/assembly-cache-tests/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
$cache=Join-Path $root 'cache';$utf8=[Text.UTF8Encoding]::new($false)
Add-Type -Path (Join-Path $project 'tests/host/AssemblyObjectCacheProbe.cs')
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
$link=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64/link.exe"
function Write-Source([string]$Path,[int]$Value){
    $text="option casemap:none`nPUBLIC boom_cache_value`n.code`nboom_cache_value PROC`n mov rax,$Value`n ret`nboom_cache_value ENDP`nEND`n"
    [IO.File]::WriteAllText($Path,$text,$utf8)
}
function Invoke-Assembly([string]$Source,[string]$Name,[bool]$Expected=$true,[switch]$NoCache){
    $object=Join-Path $root ($Name+'.obj')
    $args_=@('assemble-unit','--source',$Source,'--output',$object,'--cache',$cache)
    if($NoCache){$args_+='--no-cache'}
    $lines=& $compiler @args_ 2> (Join-Path $root ($Name+'.err'))
    $exitCode=$LASTEXITCODE;$text=$lines -join "`n"
    [IO.File]::WriteAllText((Join-Path $root ($Name+'.json')),$text,$utf8)
    $result=$text|ConvertFrom-Json
    if($result.success -ne $Expected -or (($exitCode -eq 0) -ne $Expected)){throw "Unexpected assembler result: $Name"}
    return $result
}
function Check-Code([string]$Name,[ulong]$Value){
    $dll=Join-Path $root ($Name+'.dll');$object=Join-Path $root ($Name+'.obj')
    & $link /NOLOGO /DLL /NOENTRY /MACHINE:X64 /DYNAMICBASE /NXCOMPAT "/OUT:$dll" /EXPORT:boom_cache_value $object > (Join-Path $root ($Name+'.link.log')) 2>&1
    if($LASTEXITCODE -ne 0){throw "Cache fixture link failed: $Name"}
    [BoomAssemblyObjectCacheProbe]::Check($dll,$Value)
}
$first=Join-Path $root 'first.asm';Write-Source $first 42
$cold=Invoke-Assembly $first 'cold'
if($cold.cache.status -ne 'miss'){throw 'Fresh cache must miss'}
Check-Code 'cold' 42
$second=Join-Path $root 'relocated.asm';Write-Source $second 42
$warm=Invoke-Assembly $second 'warm'
if($warm.cache.status -ne 'hit' -or $warm.cache.key -ne $cold.cache.key){throw 'Identical source at another path must hit'}
if((Get-FileHash (Join-Path $root 'cold.obj')).Hash -ne (Get-FileHash (Join-Path $root 'warm.obj')).Hash){throw 'Restored object bytes differ'}
Check-Code 'warm' 42
Write-Source $second 43
$changed=Invoke-Assembly $second 'changed'
if($changed.cache.status -ne 'miss' -or $changed.cache.key -eq $cold.cache.key){throw 'Changed source reused stale machine code'}
Check-Code 'changed' 43
$entry=Join-Path $cache ($cold.cache.key.Substring(0,2)+'/'+$cold.cache.key+'.cache')
[IO.File]::WriteAllBytes($entry,[byte[]](1,2,3,4))
$repaired=Invoke-Assembly $first 'repaired'
if($repaired.cache.status -ne 'miss' -or $repaired.cache.reason -notlike 'Rejected cached object*'){throw 'Corrupt cache was not rejected'}
Check-Code 'repaired' 42
$again=Invoke-Assembly $first 'repaired-hit'
if($again.cache.status -ne 'hit'){throw 'Corrupt cache was not repaired'}
Check-Code 'repaired-hit' 42
$disabled=Invoke-Assembly $first 'disabled' -NoCache
if($disabled.cache.status -ne 'disabled'){throw 'No-cache control unexpectedly reused an object'}
Check-Code 'disabled' 42
$invalid=Join-Path $root 'invalid.asm';[IO.File]::WriteAllText($invalid,"option casemap:none`n.code`nnot_a_real_instruction`nEND`n",$utf8)
foreach($name in @('failed-one','failed-two')){
    $failure=Invoke-Assembly $invalid $name $false
    if($failure.cache.status -ne 'miss' -or (Test-Path -LiteralPath (Join-Path $root ($name+'.obj')))){throw 'Failed assembly was cached or published'}
    $failedEntry=Join-Path $cache ($failure.cache.key.Substring(0,2)+'/'+$failure.cache.key+'.cache')
    if(Test-Path -LiteralPath $failedEntry){throw 'Failed assembly published a cache entry'}
}
$include=Join-Path $root 'external.inc';$external=Join-Path $root 'external.asm'
[IO.File]::WriteAllText($external,('option casemap:none' + "`nPUBLIC boom_cache_value`n.code`ninclude $include`nEND`n"),$utf8)
foreach($number in @(45,46)){
    [IO.File]::WriteAllText($include,"boom_cache_value PROC`n mov eax,$number`n ret`nboom_cache_value ENDP`n",$utf8)
    $name='external-'+$number;$bypass=Invoke-Assembly $external $name
    if($bypass.cache.status -ne 'bypassed' -or $bypass.cache.key){throw 'External include was reused without dependency tracking'}
    Check-Code $name ([ulong]$number)
}
# All children use the same cold key, independent output paths and a fresh cache.
$parallelCache=Join-Path $root 'parallel-cache';$children=@()
try{
    foreach($worker in 0..7){
        $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$compiler;$start.WorkingDirectory=$project
        $start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
        foreach($argument in @('assemble-unit','--source',$first,'--output',(Join-Path $root "worker-$worker.obj"),'--cache',$parallelCache)){$start.ArgumentList.Add($argument)}
        $process=[Diagnostics.Process]::new();$process.StartInfo=$start
        if(-not $process.Start()){throw 'Cannot start cache test child'}
        $children+=@{process=$process;stdout=$process.StandardOutput.ReadToEndAsync();stderr=$process.StandardError.ReadToEndAsync();worker=$worker}
    }
    foreach($child in $children){
        if(-not $child.process.WaitForExit(60000)){$child.process.Kill($true);throw 'Cache test child timed out'}
        $text=$child.stdout.GetAwaiter().GetResult();$errors=$child.stderr.GetAwaiter().GetResult()
        if($child.process.ExitCode -ne 0){throw "Cache test child failed: $errors"}
        $result=$text|ConvertFrom-Json
        if(-not $result.success -or $result.cache.status -notin @('hit','miss') -or $result.cache.reason){throw 'Concurrent cache publication failed'}
        Check-Code ('worker-'+$child.worker) 42
    }
}finally{foreach($child in $children){$child.process.Dispose()}}
$result=[ordered]@{passed=$true;scope='MASM_COFF_cache_invalidation_recovery_parallel_publication_and_executed_machine_code_fixtures';
cold_and_relocated_hit=$true;source_change_invalidated=$true;corruption_rebuilt_and_repaired=$true;failed_assemblies_not_cached=2;external_include_bypass_cases=2;no_cache_control=$true;parallel_workers=8;executed_fixture_images=16;
fixture_only=$true;game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,$utf8);Write-Output $json
