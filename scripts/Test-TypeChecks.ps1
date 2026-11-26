param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\client.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content -LiteralPath (Join-Path $projectRoot '.boom\latest-jdk-base.txt') -Raw).Trim()) 'jdk-base.json'}
$boomPath=(Resolve-Path -LiteralPath $Boom).Path
$compilerSha=(Get-FileHash -LiteralPath $boomPath).Hash.ToLowerInvariant()
$root=Join-Path $projectRoot ('.boom\type-check-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$tools=Get-Content -LiteralPath (Join-Path $projectRoot '.boom\toolchain.json') -Raw|ConvertFrom-Json
$sources=@(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'java\subset\dev\boom\typechecks') -Filter '*.java' -File|ForEach-Object FullName)
& (Join-Path (Split-Path -Parent $tools.java) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes @sources (Join-Path $projectRoot 'java\subset\dev\boom\subset\ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Type-check reference javac failed.'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
$baseArgs=@('compile-program','--entry-class','dev/boom/typechecks/TypeEntry','--assemble')
foreach($file in Get-ChildItem -LiteralPath (Join-Path $classes 'dev\boom\typechecks') -Filter '*.class' -File){$baseArgs+=@('--class-file',$file.FullName)}
$methods=@('checks','stringCast','boxCast','interfaceCast','primitiveArrayCast','stringArrayCast','covariantCast','classCast','name','mirrorIdentity','actualString','nullMetadataOnly','referenceJoin','localJoinCast','dynamicString','nullCast')
$programs=@{};$manifests=@{}
foreach($method in $methods){
    $text=& $boomPath @baseArgs --metadata-lock $MetadataLock --jdk-base $JdkBase --method $method --output (Join-Path $root $method)
    if($LASTEXITCODE -ne 0){throw "Type-check compilation failed: $method"}
    $program=$text|ConvertFrom-Json;$programs[$method]=$program;$manifests[$method]=$program.compilation
    if($method -ne 'nullCast' -and ($program.schema -ne 7 -or $program.runtime_type_map_abi -ne 1 -or $program.runtime_type_bindings.Count -lt 12)){throw 'Unexpected runtime type map contract.'}
    if(@($program.classes|Where-Object name -eq 'dev/boom/typechecks/MetadataOnly').Count -ne 0){throw 'Type resolution incorrectly requested target initialization.'}
    Write-Output "Compiled runtime type entry: $method"
}
if($programs['referenceJoin'].reference_joins.Count -eq 0 -or $programs['localJoinCast'].reference_joins.Count -eq 0){throw 'Reference joins lost their identified alternatives.'}
$cases=[Collections.Generic.List[object]]::new()
function Bits([int]$value){return ([BitConverter]::ToUInt32([BitConverter]::GetBytes($value),0)).ToString('x')}
function AddCase([string]$method,[string[]]$values){$cases.Add([pscustomobject]@{method=$method;values=$values})}
foreach($kind in (@(-1,[int]::MinValue,[int]::MaxValue)+@(0..31))){foreach($seed in @([int]::MinValue,-1,0,7,[int]::MaxValue)){
    foreach($method in @('checks','stringCast','boxCast','interfaceCast','primitiveArrayCast','stringArrayCast','covariantCast','classCast','name','mirrorIdentity','localJoinCast')){AddCase $method @((Bits $kind),(Bits $seed))}
}}
foreach($seed in @([int]::MinValue,-1,0,7,[int]::MaxValue)){
    foreach($method in @('actualString','nullMetadataOnly','referenceJoin','dynamicString','nullCast')){AddCase $method @((Bits $seed))}
}
$lines=@($cases|ForEach-Object{(@('dev.boom.typechecks.TypeEntry',$_.method,$manifests[$_.method].descriptor)+@($_.values)) -join ' '})
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$tools.java;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Type-check JVM reference failed.'}
    $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Type-check JVM input stalled.'}
    $oracle.StandardInput.Close();if(-not $oracle.WaitForExit(30000)){throw 'Type-check JVM reference timed out.'}
    if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Type-check reference count mismatch.'}
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '});$manifest=$manifests[$method]
    if((Get-FileHash -LiteralPath $manifest.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.dll_digest.sha256){throw 'Type-check module hash mismatch.'}
    $actual=[BoomNumericProbe]::Run($manifest.dll,(Join-Path $root 'fpstate.dll'),$values,'I',$manifest.requires_heap)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add([pscustomobject]@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
$destination=Join-Path $root 'reject-unverified'
& $boomPath @baseArgs --method checks --output $destination 2>&1|Out-Null
if($LASTEXITCODE -eq 0 -or (Test-Path -LiteralPath $destination)){throw 'Unverified runtime types were accepted.'}
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
Add-Type -Path (Join-Path $projectRoot 'tests\host\RuntimeTypeProbe.cs')
[BoomRuntimeTypeProbe]::AbiAndFailure((Join-Path $root 'boom-runtime.dll'))
[BoomRuntimeTypeProbe]::Cold($manifests['actualString'].dll,(Join-Path $root 'boom-runtime.dll'))
$report=[ordered]@{backend='boom-runtime-types-program-v7-masm-x64';runtime_language='assembly';runtime_type_map_abi=1;compiled_entries=$methods.Count;differential_cases=$cases.Count;native_executions=$cases.Count*2;cold_getclass_records=4099;all_primitive_array_identities=$true;checkcast_and_instanceof=$true;null_and_class_cast_exceptions=$true;object_getclass=$true;metadata_resolution_does_not_initialize_target=$true;interface_and_array_assignment_checks=$true;cast_covariance=$true;general_covariant_array_execution=$false;reference_join_alternatives_preserved=$true;dynamic_string_integration=$true;quiescent_gc_roots=$true;native_abi_and_unknown_tag_rejection=$true;failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
if((Get-FileHash -LiteralPath $boomPath).Hash.ToLowerInvariant() -ne $compilerSha){throw 'Type-check compiler changed during verification'}
$report['compiler_sha256']=$compilerSha
$json=$report|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
[IO.File]::WriteAllText((Join-Path $projectRoot '.boom/latest-type-check-test.txt'),$root,[Text.UTF8Encoding]::new($false))
if(-not $report.passed){exit 1}
