param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path (Get-Location) ('.boom/throwable-program-tests/'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) 'javac.exe') --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/throwables/ThrowableProgram.java java/subset/dev/boom/throwables/TraceReference.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'Throwable javac reference failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root
& scripts/Build-FpProbe.ps1 -Output $root
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/ThrowableProbe.cs
Add-Type -Path tests/host/UnwindProbe.cs
$common=@('compile-program','--entry-class','dev/boom/throwables/ThrowableProgram','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
foreach($file in Get-ChildItem (Join-Path $classes 'dev/boom/throwables') -Filter 'ThrowableProgram*.class'){$common+=@('--class-file',$file.FullName)}
$methods=@('message','nested','refill','shadowRefill','recursion','cause','fillInStackTrace','lambda','noMessage','reusable','parallel');$programs=@{}
foreach($method in $methods){
    & $Boom @common --method $method --output (Join-Path $root $method) > (Join-Path $root ($method+'-compile.json'))
    if($LASTEXITCODE -ne 0){throw "Throwable compilation failed: $method"}
    $p=Get-Content (Join-Path $root ($method+'/program.json')) -Raw|ConvertFrom-Json
    if($p.schema -ne 29 -or $p.java_frames.abi -ne 2 -or $p.java_frames.node_bytes -ne 48 -or $p.throwables.abi -ne 1 -or $p.initializer_source_abi -ne 2){throw 'Throwable/frame profile missing'}
    if($p.throwables.binding.origin.sha256 -ne $base.classes.'java.lang.Throwable'.sha256 -or $p.throwables.binding.caller.sha256 -ne $p.throwables.binding.origin.sha256){throw 'Throwable native binding provenance mismatch'}
    foreach($source in @('java/lang/Throwable','java/util/Collections')){if(@($p.symbols|Where-Object {$_.class_name -eq $source -and $_.method -eq '<clinit>'}).Count -ne 1){throw 'Original Throwable/Collections sentinels were not linked'}}
    if($p.java_frames.methods.Count -ne $p.symbols.Count -or @($p.java_frames.methods|Where-Object {$_.class_name -like 'dev/boom/throwables/*' -and $_.source.generated -eq $null -and ($_.source_file -ne 'ThrowableProgram.java' -or $_.lines.Count -eq 0)}).Count){throw 'Original Java frame/source/line metadata missing'}
    $programs[$method]=$p;Write-Output "Compiled original Throwable and Java shadow frames: $method"
}
$values=[Collections.Generic.List[string]]::new()
foreach($n in @(0,1,-1,[int]::MinValue,[int]::MaxValue,127,128,255,256,32767,32768,65535,65536,-65536,0xd800,0xdbff,0xdc00,0xdfff,0x1f600)){$values.Add(([BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$n),0)).ToString('x'))}
[uint64]$seed=0x12345678
for($i=0;$i -lt 96;$i++){$seed=($seed*1664525+1013904223) -band 0xffffffffL;$values.Add($seed.ToString('x'))}
function Java([string]$entry,[string]$inputText){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($a in @('-cp',$classes,$entry)){$info.ArgumentList.Add($a)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $java=[Diagnostics.Process]::new();$java.StartInfo=$info
    try{if(-not $java.Start()){throw 'Throwable JVM reference failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.StandardInput.WriteAsync($inputText).Wait(15000)){throw 'Throwable JVM input stalled'};$java.StandardInput.Close();if(-not $java.WaitForExit(30000)){throw 'Throwable JVM reference timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};return $stdout.GetAwaiter().GetResult()}
    finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
}
$lines=@(foreach($method in $methods){foreach($value in $values){'dev.boom.throwables.ThrowableProgram '+$method+' (I)I '+$value}})
$expected=@((Java 'dev.boom.subset.ClassNumericOracle' (($lines -join "`n")+"`n")).Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {$_.Trim()})
if($expected.Count -ne $lines.Count){throw 'Throwable numeric reference case count mismatch'}
$index=0
foreach($method in $methods){$actual=[BoomNumericProbe]::Run($programs[$method].compilation.dll,(Join-Path $root 'fpstate.dll'),$values.ToArray(),'I',$true);foreach($result in $actual){if($result -ne $expected[$index]){throw "Throwable JVM numeric mismatch: $method, $index, $result, $($expected[$index])"};$index++}}
$snapshotMethods=@($methods|Where-Object {$_ -ne 'parallel'});$snapshotValues=@('0','1','2','3','ffffffff','80000000','7fffffff')
$snapshotLines=@(foreach($method in $snapshotMethods){foreach($value in $snapshotValues){$method+' '+$value}})
$snapshotExpected=@((Java 'dev.boom.throwables.TraceReference' (($snapshotLines -join "`n")+"`n")).Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {$_.Trim()})
if($snapshotExpected.Count -ne $snapshotLines.Count){throw 'Throwable trace reference case count mismatch'}
$index=0
foreach($method in $snapshotMethods){
    $p=$programs[$method];[BoomThrowableProbe]::Reset()
    foreach($m in $p.java_frames.methods){[int[]]$pcs=@($m.lines|ForEach-Object {$_.pc});[int[]]$sourceLines=@($m.lines|ForEach-Object {$_.line});[BoomThrowableProbe]::MethodInfo($m.id,$m.class_name,$m.name,$m.source_file,$pcs,$sourceLines)}
    $owner=@($p.classes|Where-Object name -eq 'dev/boom/throwables/ThrowableProgram')[0];$field=@($owner.fields|Where-Object name -eq 'last')[0]
    [uint[]]$numbers=@($snapshotValues|ForEach-Object {[Convert]::ToUInt32($_,16)})
    $actual=[BoomThrowableProbe]::Snapshots($p.compilation.dll,(Join-Path $root 'boom-runtime.dll'),$owner.id,$field.index,$numbers)
    foreach($trace in $actual){if($trace -ne $snapshotExpected[$index]){throw "Real Java stack trace mismatch: $method, $index`nNative: $trace`nJVM: $($snapshotExpected[$index])"};$index++}
    Write-Output "Validated original construction, method/file/line snapshots and roots: $method"
}
$p=$programs.parallel
[BoomThrowableProbe]::Parallel($p.compilation.dll,(Join-Path $root 'boom-runtime.dll'))
[BoomThrowableProbe]::FrameAbi($p.compilation.dll,(Join-Path $root 'boom-runtime.dll'))
$p=$programs.reusable;[BoomThrowableProbe]::Reset()
foreach($m in $p.java_frames.methods){[int[]]$pcs=@($m.lines|ForEach-Object {$_.pc});[int[]]$sourceLines=@($m.lines|ForEach-Object {$_.line});[BoomThrowableProbe]::MethodInfo($m.id,$m.class_name,$m.name,$m.source_file,$pcs,$sourceLines)}
$owner=@($p.classes|Where-Object name -eq 'dev/boom/throwables/ThrowableProgram')[0];$field=@($owner.fields|Where-Object name -eq 'last')[0]
[BoomThrowableProbe]::TraceOom($p.compilation.dll,(Join-Path $root 'boom-runtime.dll'),$owner.id,$field.index)
foreach($method in @('throwing','caught')){
    $out=Join-Path $root ('context32-'+$method)
    & $Boom @common --method $method --output $out > (Join-Path $root ($method+'-context32.json'))
    if($LASTEXITCODE -ne 0){throw 'Verified exception boundary did not upgrade to Context32'}
    $p=Get-Content (Join-Path $out 'program.json') -Raw|ConvertFrom-Json
    if($p.schema -ne 30 -or $p.exception_runtime.context_bytes -ne 32){throw 'Throwable boundary used a truncated Context16 call chain'}
    if($method -eq 'throwing'){$type=@($p.classes|Where-Object name -eq 'java/lang/IllegalStateException')[0];[BoomUnwindProbe]::Uncaught($p.compilation.dll,$type.id)}
    else{$actual=[BoomNumericProbe]::Run($p.compilation.dll,(Join-Path $root 'fpstate.dll'),[string[]]@('0','1','2'),'I',$true);if(($actual -join '|') -ne 'v 0000000000000013|v 0000000000000064|v 0000000000000032'){throw 'Throwable Context32 catch boundary failed'}}
}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Throwable compiler changed during run'}
$report=[ordered]@{backend='boom-throwable-frames-program-v29-masm-x64';compiler_sha256=$sha;runtime_language='assembly';compiled_entries=$methods.Count;differential_cases=$lines.Count;native_executions=($lines.Count*2);real_JVM_trace_comparisons=$snapshotLines.Count;multicore_records=6147;workers=8;original_Throwable_and_Collections_initializers=$true;original_constructor_chains_and_cause_identity=$true;actual_method_BCI_file_and_line_capture=$true;constructor_prefix_and_generated_lambda_filtering=$true;shadowed_subclass_fields_preserved=$true;per_thread_generated_frame_chain=$true;frame_nodes_on_native_method_stack=$true;quiescent_TLS_release_and_busy_rejection=$true;trace_OOM_suppressed_with_Java_sentinel_and_recovery=$true;trace_graph_survives_collection=$true;temporary_graph_reclaimed=$true;Context32_boundary_entries=2;Java_athrow_and_catch_boundary_execution=$true;Java_StackTraceElement_materialization_complete=$false;automatic_gc=$false;System_application_bootstrap_complete=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 7
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-throwable-program.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
