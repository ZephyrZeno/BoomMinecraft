param([string]$Boom='target\release\boom.exe')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$boomPath=(Resolve-Path -LiteralPath $Boom).Path
$tools=Get-Content -LiteralPath (Join-Path $projectRoot '.boom\toolchain.json') -Raw|ConvertFrom-Json
$java=$tools.java;$javac=Join-Path (Split-Path -Parent $java) 'javac.exe'
$root=Join-Path $projectRoot ('.boom\state-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$sources=@(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'java\subset\dev\boom\state') -Filter '*.java' -File|ForEach-Object FullName)
& $javac --release 21 -proc:none -encoding UTF-8 -d $classes @sources (Join-Path $projectRoot 'java\subset\dev\boom\subset\ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Linked fixtures javac failed.'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
$classFiles=@(Get-ChildItem -LiteralPath (Join-Path $classes 'dev\boom\state') -Filter '*.class' -File|Sort-Object Name|ForEach-Object FullName)
$methods=@('constants','longValue','floatValue','doubleValue','narrow','table','cycle','reentry','volatileField')
$manifests=@{};$programs=@{}
$baseArgs=@('compile-program','--entry-class','dev/boom/state/StateEntry','--assemble')
foreach($file in $classFiles){$baseArgs+=@('--class-file',$file)}
foreach($method in $methods){
    $text=& $boomPath @baseArgs --method $method --output (Join-Path $root $method)
    if($LASTEXITCODE -ne 0){throw "Class state compilation failed: $method"}
    $program=$text|ConvertFrom-Json;$programs[$method]=$program;$manifests[$method]=$program.compilation
    if($method -ne 'volatileField' -and -not @($program.classes|Where-Object { $null -ne $_.initializer }).Count){throw 'Initializer was not linked.'}
    if($method -eq 'volatileField' -and ($program.schema -ne 12 -or -not $program.volatile_accesses)){throw 'Volatile static read did not select the ordering contract.'}
}
$cases=[Collections.Generic.List[object]]::new()
function Add-Case([string]$Method,[string[]]$Values){$cases.Add([pscustomobject]@{method=$Method;values=$Values})}
Add-Case 'volatileField' @()
$ints=@('0','1','ffffffff','80000000','7fffffff','12345678','8000','ffff8000')
$longs=@('0','1','ffffffffffffffff','8000000000000000','7fffffffffffffff','123456789abcdef')
$floats=@('0','80000000','3f800000','bf800000','7f800000','ff800000','7fc00000','7f800001','1','7fffff','800000','7f7fffff')
$doubles=@('0','8000000000000000','3ff0000000000000','bff0000000000000','7ff0000000000000','fff0000000000000','7ff8000000000000','7ff0000000000001','1','fffffffffffff','10000000000000','7fefffffffffffff')
foreach($a in $ints){foreach($method in @('constants','narrow','cycle','reentry')){Add-Case $method @($a)}}
foreach($a in $longs){Add-Case 'longValue' @($a)}
foreach($a in $floats){Add-Case 'floatValue' @($a)}
foreach($a in $doubles){Add-Case 'doubleValue' @($a)}
foreach($index in @(-1,0,1,7,31,32,[int]::MinValue,[int]::MaxValue)){
    $bitsIndex=([BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$index),0)).ToString('x')
    foreach($seed in $ints){Add-Case 'table' @($bitsIndex,$seed)}
}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$java;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Cannot start array JVM oracle.'}
    $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    $lines=@($cases|ForEach-Object{(@('dev.boom.state.StateEntry',$manifests[$_.method].method,$manifests[$_.method].descriptor)+@($_.values)-join ' ').TrimEnd()})
    $write=$oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n")
    if(-not $write.Wait(15000)){$oracle.Kill($true);$oracle.WaitForExit();throw 'Program oracle input stalled.'}
    $oracle.StandardInput.Close()
    if(-not $oracle.WaitForExit(30000)){$oracle.Kill($true);$oracle.WaitForExit();throw 'Program JVM oracle timed out.'}
    if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Program oracle count mismatch.'}
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '});$manifest=$manifests[$method]
    if((Get-FileHash -LiteralPath $manifest.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.dll_digest.sha256){throw 'Program DLL hash mismatch.'}
    $actual=[BoomNumericProbe]::Run($manifest.dll,(Join-Path $root 'fpstate.dll'),$values,[char]$manifest.descriptor[-1],[bool]$manifest.requires_heap)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add([pscustomobject]@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
$rejections=0
foreach($method in @('objectField')){
    & $boomPath @baseArgs --method $method --output (Join-Path $root ('reject-'+$method)) 2>&1|Out-Null
    if($LASTEXITCODE -eq 0){throw "Unsupported static field accepted: $method"};$rejections++
}
$persistent=@('failure','failureArray','failureOom','failureNested','counter','race')
foreach($method in $persistent){
    $text=& $boomPath @baseArgs --method $method --output (Join-Path $root $method)
    if($LASTEXITCODE -ne 0){throw "Persistent state compilation failed: $method"}
    $program=$text|ConvertFrom-Json;$programs[$method]=$program;$manifests[$method]=$program.compilation
}
$sequence=[Collections.Generic.List[object]]::new()
foreach($method in @('failure','failureArray','failureOom','failureNested')){for($i=0;$i -lt 4;$i++){$sequence.Add([pscustomobject]@{method=$method;values=@()})}}
foreach($seed in $ints){$sequence.Add([pscustomobject]@{method='counter';values=@($seed)})}
$sequence.Add([pscustomobject]@{method='race';values=@('0')})
$seqInfo=[Diagnostics.ProcessStartInfo]::new();$seqInfo.FileName=$java;$seqInfo.UseShellExecute=$false;$seqInfo.CreateNoWindow=$true
$seqInfo.RedirectStandardInput=$true;$seqInfo.RedirectStandardOutput=$true;$seqInfo.RedirectStandardError=$true
foreach($arg in @('-Xmx64m','-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$seqInfo.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$seqInfo.Environment.Remove($key)|Out-Null}
$seqOracle=[Diagnostics.Process]::new();$seqOracle.StartInfo=$seqInfo
try{
    if(-not $seqOracle.Start()){throw 'State sequence JVM failed.'}
    $seqOut=$seqOracle.StandardOutput.ReadToEndAsync();$seqErr=$seqOracle.StandardError.ReadToEndAsync()
    $lines=@($sequence|ForEach-Object{(@('dev.boom.state.StateEntry',$_.method,$manifests[$_.method].descriptor)+@($_.values)-join ' ').TrimEnd()})
    if(-not $seqOracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'State sequence input timeout.'}
    $seqOracle.StandardInput.Close();if(-not $seqOracle.WaitForExit(30000)){throw 'State sequence JVM timeout.'}
    if($seqOracle.ExitCode -ne 0){throw $seqErr.GetAwaiter().GetResult()}
    $seqExpected=@($seqOut.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $seqOracle.HasExited){$seqOracle.Kill($true);$seqOracle.WaitForExit()};$seqOracle.Dispose()}
if($seqExpected.Count -ne $sequence.Count){throw 'State sequence count mismatch.'}
Add-Type -Path (Join-Path $projectRoot 'tests\host\ClassStateProbe.cs')
foreach($method in @('failure','failureArray','failureOom','failureNested','counter')){
    $indices=@(for($i=0;$i -lt $sequence.Count;$i++){if($sequence[$i].method -eq $method){$i}})
    [string[]]$inputsSequence=@($indices|ForEach-Object{$sequence[$_].values -join ' '})
    $manifest=$manifests[$method];$actual=[BoomClassStateProbe]::Sequence($manifest.dll,$inputsSequence,[bool]$manifest.requires_heap)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $seqExpected[$i]){$failures.Add([pscustomobject]@{case=$sequence[$i];expected=$seqExpected[$i];actual=$actual[$n]})}}
}
foreach($case in @(@('failure','Failure',8,1,5,0),@('failureArray','FailureArray',8,1,12,1),@('failureOom','FailureOom',3,3,2,0),@('failureNested','FailureParent',8,8,0,0))){
    $method=$case[0];$className='dev/boom/state/'+$case[1];$state=@($programs[$method].classes|Where-Object name -eq $className)[0]
    [BoomClassStateProbe]::CheckFailure($manifests[$method].dll,[bool]$manifests[$method].requires_heap,[uint32]$state.id,[uint32]$state.initializer,[uint32]$case[2],[uint32]$case[3],[uint32]$case[4],[int]$case[5])
}
$constants=@($programs['constants'].classes|Where-Object name -eq 'dev/boom/state/Constants')[0]
$expectedConstants=@{I='0000000089abcdef';J='8000000000000000';F='0000000080000000';D='7ff8000000000000';Z='1';B='00000000ffffff8f';S='00000000ffffcfc7';C='ffe1'}
foreach($name in $expectedConstants.Keys){$field=@($constants.fields|Where-Object name -eq $name)[0];[BoomClassStateProbe]::CheckField($manifests['constants'].dll,[uint32]$constants.id,[uint32]$field.index,[Convert]::ToUInt64($expectedConstants[$name],16))}
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
$raceState=@($programs['race'].classes|Where-Object name -eq 'dev/boom/state/Race')[0]
$runs=@($raceState.fields|Where-Object name -eq 'runs')[0]
$raceExpected=[Convert]::ToUInt32(($seqExpected[-1] -split ' ')[1],16)
[BoomClassStateProbe]::ColdParallel($manifests['race'].dll,(Join-Path $root 'boom-runtime.dll'),[uint32]$raceState.id,[uint32]$runs.index,$raceExpected)
foreach($case in @(@('failure','Failure',0),@('failureArray','FailureArray',1))){
    $method=$case[0];$state=@($programs[$method].classes|Where-Object name -eq ('dev/boom/state/'+$case[1]))[0]
    $entry=@($programs[$method].symbols|Where-Object {$_.class_name -eq 'dev/boom/state/StateEntry' -and $_.method -eq $method})[0]
    [BoomClassStateProbe]::FailureParallel($manifests[$method].dll,(Join-Path $root 'boom-runtime.dll'),[bool]$manifests[$method].requires_heap,[uint32]$state.id,[uint32]$entry.id,[uint32]$state.initializer,[int]$case[2])
}
$stackSource=Join-Path $root 'StackEntry.java';$stackClasses=Join-Path $root 'sc'
$sourceText="package dev.boom.stack; public final class StackEntry { public static int run(){ return C0.value; } }`n"
for($i=0;$i -lt 144;$i++){$value=if($i -eq 143){'1'}else{'C'+($i+1)+'.value+1'};$sourceText+='final class C'+$i+' { static int value='+$value+'; }'+"`n"}
[IO.File]::WriteAllText($stackSource,$sourceText,[Text.UTF8Encoding]::new($false))
& $javac --release 21 -proc:none -d $stackClasses $stackSource
if($LASTEXITCODE -ne 0){throw 'Stack chain javac failed.'}
$stackArgs=@('compile-program','--entry-class','dev/boom/stack/StackEntry','--method','run','--output',(Join-Path $root 'stack'),'--assemble')
foreach($file in Get-ChildItem -LiteralPath (Join-Path $stackClasses 'dev\boom\stack') -Filter '*.class' -File){$stackArgs+=@('--class-file',$file.FullName)}
$text=& $boomPath @stackArgs;if($LASTEXITCODE -ne 0){throw 'Stack chain compilation failed.'}
$stackProgram=$text|ConvertFrom-Json
[uint32[]]$chainIds=@(for($i=0;$i -lt 144;$i++){(@($stackProgram.classes|Where-Object name -eq ('dev/boom/stack/C'+$i))[0]).id})
[BoomClassStateProbe]::StackLimit($stackProgram.compilation.dll,$chainIds)
$report=[ordered]@{backend='boom-object-program-v3-masm-x64';runtime_language='assembly';compiled_entries=($methods.Count+$persistent.Count+1);differential_entries=$methods.Count;differential_cases=$cases.Count;native_executions=$cases.Count*2;primitive_static_fields=$true;class_initializers=$true;same_thread_reentry=$true;cyclic_class_initialization=$true;static_array_roots_preserved=$true;persistent_jvm_sequence_cases=$sequence.Count;original_failure_retained=$true;constant_value_preparation=$true;heap_rebinding_rejected=$true;nested_initializer_failure=$true;cold_parallel_records=4099;initializer_once_publication_checked=$true;concurrent_failure_records=16396;failed_static_roots_retained=$true;dynamic_guest_frame_limit=128;deep_initializer_chain_checked=$true;rejected_features=$rejections;failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1};exit 0
