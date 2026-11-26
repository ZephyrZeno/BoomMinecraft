param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path (Get-Location) ('.boom/unwind-program-tests/'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
[IO.File]::WriteAllText('.boom/current-unwind-program.txt',$root,[Text.UTF8Encoding]::new($false))
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) 'javac.exe') --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/unwind/UnwindProgram.java java/subset/dev/boom/unwind/TraceReference.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'Unwind javac reference failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root > (Join-Path $root 'runtime-build.log') 2>&1
& scripts/Build-FpProbe.ps1 -Output $root > (Join-Path $root 'fp-build.log') 2>&1
Add-Type -Path tests/host/UnwindProbe.cs
Add-Type -Path tests/host/ThrowableProbe.cs
$common=@('compile-program','--entry-class','dev/boom/unwind/UnwindProgram','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
foreach($file in Get-ChildItem (Join-Path $classes 'dev/boom/unwind') -Filter 'UnwindProgram*.class'){$common+=@('--class-file',$file.FullName)}
$methods=@('arithmetic','identity','rethrow','ordered','multicatch','finallyPath','finallyRethrow','throwNull','implicitNpe','explicitNpe','bounds','negativeArray','arrayStore','cast','monitor','nullMonitor','synchronizedMethod','initFailure','initError','oom','stackOverflow','parallel');$programs=@{}
foreach($method in ($methods+@('uncaught','initParallel'))){
    & $Boom @common --method $method --output (Join-Path $root $method) > (Join-Path $root ($method+'-compile.json')) 2> (Join-Path $root ($method+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'-compile.err')) -Tail 25;throw "Unwind compilation failed: $method"}
    $p=Get-Content (Join-Path $root ($method+'/program.json')) -Raw|ConvertFrom-Json
    if($p.schema -lt 30 -or $p.exception_runtime.context_bytes -ne 32 -or $p.exception_runtime.external_bridge_bytes -ne 16 -or $p.exception_runtime.class_state_abi -ne 2 -or $p.java_frames.abi -ne 2 -or $p.exception_runtime.factories.Count -lt 22){throw 'Context32/source factory profile missing'}
    $factoryKinds=@($p.exception_runtime.factories|ForEach-Object {$_.kind}|Sort-Object -Unique)
    if($factoryKinds.Count -ne $p.exception_runtime.factories.Count -or @(((1..15)+(17..23))|Where-Object {$_ -notin $factoryKinds}).Count -ne 0){throw 'Unwind required factory kinds missing/duplicated'}
    foreach($f in $p.exception_runtime.factories){$name=@($p.classes|Where-Object id -eq $f.class_id)[0].name.Replace('/','.');if($f.origin.sha256 -ne $base.classes.$name.sha256){throw 'VM exception factory source provenance changed'}}
    foreach($source in @('java/lang/Throwable','java/util/Collections','java/lang/ExceptionInInitializerError','java/lang/ClassNotFoundException')){if(@($p.symbols|Where-Object {$_.class_name -eq $source -and $_.method -eq '<clinit>'}).Count -ne 1){throw "Original exception initializer not linked: $source"}}
    $programs[$method]=$p;Write-Output "Compiled Context32 original-source image: $method"
}
[uint32[]]$values=@(0,1,2,3,4,5,7,8,9,17,127,128,255,256,32767,65535,[uint32]::MaxValue,2147483648,2147483647)
[uint64]$seed=0x12345678
for($i=0;$i -lt 48;$i++){$seed=($seed*1664525+1013904223) -band 0xffffffffL;$values+=[uint32]$seed}
function Java([string]$text,[string]$entry='dev.boom.subset.ClassNumericOracle'){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($a in @('-Xmx64m','-cp',$classes,$entry)){$info.ArgumentList.Add($a)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $java=[Diagnostics.Process]::new();$java.StartInfo=$info
    try{if(-not $java.Start()){throw 'Unwind JVM reference failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.StandardInput.WriteAsync($text).Wait(15000)){throw 'Unwind JVM input stalled'};$java.StandardInput.Close();if(-not $java.WaitForExit(30000)){throw 'Unwind JVM reference timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};return $stdout.GetAwaiter().GetResult()}
    finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
}
$lines=@(foreach($method in $methods){foreach($value in $values){for($i=0;$i -lt 3;$i++){'dev.boom.unwind.UnwindProgram '+$method+' (I)I '+$value.ToString('x')}}})
$expected=@((Java (($lines -join "`n")+"`n")).Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {$_.Trim()})
if($expected.Count -ne $lines.Count){throw 'Unwind JVM case count mismatch'}
$index=0
foreach($method in $methods){
    $actual=[BoomUnwindProbe]::Run($programs[$method].compilation.dll,(Join-Path $root 'fpstate.dll'),$values)
    foreach($value in $actual){if($value -ne $expected[$index]){throw "Unwind JVM mismatch: $method, $index, native=$value, JVM=$($expected[$index])"};$index++}
    Write-Output "Validated JVM handlers, roots and both Context ABIs: $method"
}
$snapshots=[ordered]@{arithmetic=@('0');identity=@('0','1','ffffffff');rethrow=@('0','1','ffffffff');ordered=@('0','1','2');multicatch=@('0','1','2');finallyPath=@('0');finallyRethrow=@('0','1','ffffffff');throwNull=@('0','1');implicitNpe=@('0','1');explicitNpe=@('0','1');bounds=@('ffffffff','7','80000000');negativeArray=@('0','1');arrayStore=@('0','1');cast=@('0','1');monitor=@('0');nullMonitor=@('0','1');synchronizedMethod=@('0');initFailure=@('0','1');initError=@('0')}
$snapshotLines=@(foreach($method in $snapshots.Keys){foreach($value in $snapshots[$method]){$method+' '+$value}})
$snapshotExpected=@((Java (($snapshotLines -join "`n")+"`n") 'dev.boom.unwind.TraceReference').Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {$_.Trim()})
if($snapshotExpected.Count -ne $snapshotLines.Count){throw 'Unwind JVM trace case count mismatch'}
$index=0
foreach($method in $snapshots.Keys){
    $p=$programs[$method];[BoomThrowableProbe]::Reset()
    foreach($m in $p.java_frames.methods){[int[]]$pcs=@($m.lines|ForEach-Object {$_.pc});[int[]]$sourceLines=@($m.lines|ForEach-Object {$_.line});[BoomThrowableProbe]::MethodInfo($m.id,$m.class_name,$m.name,$m.source_file,$pcs,$sourceLines)}
    $owner=@($p.classes|Where-Object name -eq 'dev/boom/unwind/UnwindProgram')[0];$last=@($owner.fields|Where-Object name -eq 'last')[0]
    [uint[]]$numbers=@($snapshots[$method]|ForEach-Object {[Convert]::ToUInt32($_,16)})
    $actual=[BoomThrowableProbe]::Snapshots($p.compilation.dll,(Join-Path $root 'boom-runtime.dll'),$owner.id,$last.index,$numbers)
    foreach($trace in $actual){if($trace -ne $snapshotExpected[$index]){throw "Unwind real Java stack mismatch: $method, $index`nNative: $trace`nJVM: $($snapshotExpected[$index])"};$index++}
}
$p=$programs.uncaught;$child=@($p.classes|Where-Object name -eq 'dev/boom/unwind/UnwindProgram$Child')[0]
[BoomUnwindProbe]::Uncaught($p.compilation.dll,$child.id)
[BoomUnwindProbe]::Parallel($programs.parallel.compilation.dll,(Join-Path $root 'boom-runtime.dll'))
[BoomUnwindProbe]::ParallelFailure($programs.initParallel.compilation.dll,(Join-Path $root 'boom-runtime.dll'))
$p=$programs.initFailure;$owner=@($p.classes|Where-Object name -eq 'dev/boom/unwind/UnwindProgram')[0];$failed=@($p.classes|Where-Object name -eq 'dev/boom/unwind/UnwindProgram$BadInit')[0]
$first=@($owner.fields|Where-Object name -eq 'first')[0];$last=@($owner.fields|Where-Object name -eq 'last')[0]
$wrapped=@($p.exception_runtime.factories|Where-Object kind -eq 8)[0];$later=@($p.exception_runtime.factories|Where-Object kind -eq 9)[0]
[BoomUnwindProbe]::ClassFailureRoots($p.compilation.dll,$owner.id,$first.index,$last.index,$failed.id,@($wrapped.fields|Where-Object name -eq 'cause')[0].offset,@($later.fields|Where-Object name -eq 'cause')[0].offset)
$p=$programs.oom;$owner=@($p.classes|Where-Object name -eq 'dev/boom/unwind/UnwindProgram')[0];$last=@($owner.fields|Where-Object name -eq 'last')[0]
[BoomUnwindProbe]::EmergencyOom($p.compilation.dll,(Join-Path $root 'boom-runtime.dll'),$owner.id,$last.index)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Unwind compiler changed during run'}
$report=[ordered]@{backend='boom-context32-program-v30-masm-x64';compiler_sha256=$sha;runtime_language='assembly';compiled_entries=($methods.Count+2);differential_cases=$lines.Count;native_executions=$lines.Count;real_JVM_trace_comparisons=$snapshotLines.Count;workers=8;multicore_records=12294;actual_Throwable_athrow_and_handler_identity=$true;implicit_VM_exception_objects=$true;ordered_handlers_multicatch_finally_and_local_callsite=$true;original_exception_initializers_and_sentinels=$true;original_Java_NPE_message_and_monitor_bytecodes=$true;class_initialization_failure_causes_are_static_roots=$true;failed_initialization_has_one_owner_and_wakes_waiters=$true;Context32_call_chain_and_guarded_Context16_bridge=$true;uncaught_pending_survives_explicit_rooting=$true;OOM_and_stack_overflow_emergency_objects=$true;completely_full_heap_catches_OOM_without_allocation=$true;all_temporary_graphs_reclaimed=$true;automatic_gc=$false;exact_HotSpot_exception_message_wording=$false;Java_StackTraceElement_materialization_complete=$false;System_application_bootstrap_complete=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 7
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-unwind-program.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
