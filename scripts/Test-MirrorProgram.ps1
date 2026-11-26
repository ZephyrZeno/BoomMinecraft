param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\client.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content -LiteralPath (Join-Path $projectRoot '.boom\latest-jdk-base.txt') -Raw).Trim()) 'jdk-base.json'}
$boomPath=(Resolve-Path -LiteralPath $Boom).Path
$compilerSha=(Get-FileHash $boomPath).Hash.ToLowerInvariant()
$root=Join-Path $projectRoot ('.boom\mirror-program-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$tools=Get-Content -LiteralPath (Join-Path $projectRoot '.boom\toolchain.json') -Raw|ConvertFrom-Json
$sources=@(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'java\subset\dev\boom\mirrors') -Filter '*.java' -File|ForEach-Object FullName)
& (Join-Path (Split-Path -Parent $tools.java) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes @sources (Join-Path $projectRoot 'java\subset\dev\boom\subset\ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Class mirror reference javac failed.'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
$baseArgs=@('compile-program','--entry-class','dev/boom/mirrors/ClassEntry','--assemble')
foreach($file in Get-ChildItem -LiteralPath (Join-Path $classes 'dev\boom\mirrors') -Filter '*.class' -File){$baseArgs+=@('--class-file',$file.FullName)}
$metadataArgs=@('--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase)
$methods=@('nameHash','mirrorMix','flags','parent','component','primitiveRelation','assignable','identity','array','nullElement','nullReceiver','nullArgument','state','primitiveField')
$programs=@{};$manifests=@{}
foreach($method in $methods){
    $text=& $boomPath @baseArgs @metadataArgs --method $method --output (Join-Path $root $method)
    if($LASTEXITCODE -ne 0){throw "Class mirror compilation failed: $method"}
    $program=$text|ConvertFrom-Json;$programs[$method]=$program;$manifests[$method]=$program.compilation
    if($method -eq 'primitiveField'){
        if($program.schema -ne 20 -or $program.primitive_class_bindings.Count -ne 1){throw 'Primitive class literal did not execute the verified Integer initializer.'}
    }elseif($program.schema -ne 10 -or $program.backend -ne 'boom-compact-program-v10-masm-x64' -or $program.bootstrap_mirror_abi -ne 1 -or $null -ne $program.assertion_policy -or @($program.vm_bindings).Count -ne 0 -or -not $program.compilation.requires_heap){throw 'Unexpected legacy Class mirror runtime contract with compact application layouts.'}
    if(@($program.classes|Where-Object name -in @('dev/boom/mirrors/Child','dev/boom/mirrors/Base','dev/boom/mirrors/ClassFailure')).Count -ne 0){throw 'Class literal incorrectly requested target initialization.'}
    Write-Output "Compiled Class mirror entry: $method"
}
$cases=[Collections.Generic.List[object]]::new()
function Bits([int]$value){return ([BitConverter]::ToUInt32([BitConverter]::GetBytes($value),0)).ToString('x')}
function AddCase([string]$method,[string[]]$values){$cases.Add([pscustomobject]@{method=$method;values=$values})}
AddCase 'primitiveField' @()
foreach($which in (@(-1,[int]::MinValue,[int]::MaxValue)+@(0..31))){
    AddCase 'mirrorMix' @((Bits $which),(Bits ([int]::MinValue)))
    foreach($method in @('nameHash','flags','parent','component','primitiveRelation','identity','nullReceiver','nullArgument','state')){AddCase $method @((Bits $which))}
}
foreach($target in 0..15){foreach($source in 0..15){AddCase 'assignable' @((Bits $target),(Bits $source))}}
foreach($count in @(-1,0,1,2,7,17)){foreach($index in @(-1,0,1,($count-1),$count)){
    AddCase 'nullElement' @((Bits $count),(Bits $index))
    foreach($which in @(0,3,6,8,9,14)){AddCase 'array' @((Bits $count),(Bits $index),(Bits $which))}
}}
$lines=@($cases|ForEach-Object{(@('dev.boom.mirrors.ClassEntry',$_.method,$manifests[$_.method].descriptor)+@($_.values)) -join ' '})
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$tools.java;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Class mirror JVM reference failed.'}
    $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Class mirror JVM input stalled.'}
    $oracle.StandardInput.Close();if(-not $oracle.WaitForExit(30000)){throw 'Class mirror JVM reference timed out.'}
    if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Class mirror reference count mismatch.'}
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '});$manifest=$manifests[$method]
    if((Get-FileHash -LiteralPath $manifest.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.dll_digest.sha256){throw 'Class mirror module hash mismatch.'}
    $actual=[BoomNumericProbe]::Run($manifest.dll,(Join-Path $root 'fpstate.dll'),$values,'I',$true)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add([pscustomobject]@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
$rejections=0
foreach($method in @('unsupportedReflection')){
    $destination=Join-Path $root ('reject-'+$method)
    & $boomPath @baseArgs @metadataArgs --method $method --output $destination 2>&1|Out-Null
    if($LASTEXITCODE -eq 0 -or (Test-Path -LiteralPath $destination)){throw 'Unsupported reflection/bootstrap field execution was accepted.'};$rejections++
}
$destination=Join-Path $root 'reject-unverified'
& $boomPath @baseArgs --method nameHash --output $destination 2>&1|Out-Null
if($LASTEXITCODE -eq 0 -or (Test-Path -LiteralPath $destination)){throw 'Unverified Class mirror was accepted.'};$rejections++
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
Add-Type -Path (Join-Path $projectRoot 'tests\host\MirrorProgramProbe.cs')
$index=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq 'nameHash' -and $cases[$i].values[0] -eq '3'){$i}})[0]
$hash=[Convert]::ToUInt32($expected[$index].Substring(2),16)
[BoomMirrorProgramProbe]::Cold($manifests['nameHash'].dll,(Join-Path $root 'boom-runtime.dll'),$hash)
[BoomMirrorProgramProbe]::AbiAndFailure((Join-Path $root 'boom-runtime.dll'))
$report=[ordered]@{backend='boom-compact-program-v10-masm-x64';compiler_sha256=$compilerSha;primitive_program_schema=20;runtime_language='assembly';mirror_pool_abi=1;assertion_policy_required=$false;compiled_entries=$methods.Count;differential_cases=$cases.Count;native_executions=$cases.Count*2;cold_mirror_records=4099;source_verified_bootstrap_metadata=$true;class_literal_does_not_initialize_target=$true;metadata_hierarchy_and_array_covariance=$true;primitive_mirrors_via_array_component=$true;primitive_TYPE_field_execution=$true;mirror_and_name_gc_roots=$true;class_reference_arrays=$true;native_failure_and_heap_binding=$true;unsupported_operations_rejected=$rejections;failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
if((Get-FileHash $boomPath).Hash.ToLowerInvariant() -ne $compilerSha){throw 'Mirror compiler changed during verification'}
$json=$report|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1}
exit 0
