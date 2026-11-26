param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\client.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$compilerSha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path (Get-Location) ('.boom/monitor-program-tests/'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/monitors/MonitorEntry.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'Monitor javac reference failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root
& scripts/Build-FpProbe.ps1 -Output $root
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/MonitorProbe.cs
[BoomMonitorProbe]::Abi((Join-Path $root 'boom-runtime.dll'))
Write-Output 'Monitor runtime ABI, ownership, node reuse and contention passed.'
$argsList=@('compile-program','--entry-class','dev/boom/monitors/MonitorEntry','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
$files=@(Get-ChildItem (Join-Path $classes 'dev/boom/monitors') -Filter '*.class')
foreach($file in $files){$argsList+=@('--class-file',$file.FullName)}
$methods=@('staticEntry','recursiveStatic','recursiveInstance','instance','throwing','nullReceiver','wide','floating','nested','voidResult','abstractDispatch','inputStream','parallelStatic','parallelInstance')
$programs=@{}
foreach($method in $methods){
    $text=& $Boom @argsList --method $method --output (Join-Path $root $method)
    if($LASTEXITCODE -ne 0){throw "Synchronized compilation failed: $method; $root"};$p=$text|ConvertFrom-Json;$programs[$method]=$p
    if($method -ne 'nullReceiver' -and ($p.schema -ne 18 -or $p.monitor_methods.Count -eq 0)){throw 'Missing synchronized method envelope/metadata'}
    if($method -eq 'abstractDispatch' -and @($p.symbols|Where-Object { $_.class_name -eq 'dev/boom/monitors/AbstractReader' -and $_.method -eq 'value' }).Count){throw 'Impossible abstract receiver introduced its overridden body'}
    foreach($binding in $p.monitor_methods){$source=@($p.sources|Where-Object class_name -eq $binding.class_name)[0];if($binding.source_sha256 -ne $source.digest.sha256 -or $binding.loader -ne $source.origin.loader -or $binding.static_method -ne ($null -ne $binding.mirror_type)){throw 'Monitor source or static mirror binding mismatch'}}
    if($method -eq 'inputStream'){
        $base=Get-Content $JdkBase -Raw|ConvertFrom-Json;$source=@($p.sources|Where-Object class_name -eq 'java/io/ByteArrayInputStream')[0]
        if($source.digest.sha256 -ne $base.classes.'java.io.ByteArrayInputStream'.sha256 -or @($p.monitor_methods|Where-Object class_name -eq 'java/io/ByteArrayInputStream').Count -lt 4){throw 'Original JDK synchronized InputStream implementation was not compiled'}
    }
    Write-Output "Compiled synchronized entry: $method"
}
$cases=[Collections.Generic.List[object]]::new()
$ints=@('0','1','2','f','10','ffffffff','80000000','7fffffff')
foreach($method in @('staticEntry','recursiveStatic','recursiveInstance','instance','throwing','nullReceiver','nested','voidResult','abstractDispatch','inputStream')){foreach($a in $ints){$cases.Add(@{method=$method;values=@($a)})}}
foreach($a in @('0','1','ffffffffffffffff','8000000000000000','7fffffffffffffff','ffffffff00000000')){foreach($b in @('0','1','ffffffffffffffff','8000000000000000')){$cases.Add(@{method='wide';values=@($a,$b)})}}
$ds=@('0','8000000000000000','3ff0000000000000','bff0000000000000','1','7ff0000000000000','fff0000000000000','7ff8000000000001')
foreach($a in $ds){foreach($b in $ds){$cases.Add(@{method='floating';values=@($a,$b)})}}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Monitor JVM oracle failed'};$stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    $lines=@($cases|ForEach-Object{(@('dev.boom.monitors.MonitorEntry',$_.method,$programs[$_.method].compilation.descriptor)+$_.values) -join ' '})
    if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Monitor oracle input stalled'};$oracle.StandardInput.Close()
    if(-not $oracle.WaitForExit(30000)){throw 'Monitor JVM reference timed out'};if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Monitor oracle count mismatch'}
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods|Where-Object {$_ -notlike 'parallel*'}){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}});$p=$programs[$method]
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '})
    $actual=[BoomNumericProbe]::Run($p.compilation.dll,(Join-Path $root 'fpstate.dll'),$values,$p.compilation.descriptor[-1],$true)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add(@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
if($failures.Count){$failures|ConvertTo-Json -Depth 8|Set-Content (Join-Path $root 'failures.json');throw "Monitor differential mismatches: $($failures.Count), $root"}
foreach($method in @('parallelStatic','parallelInstance')){[BoomMonitorProbe]::Parallel($programs[$method].compilation.dll,(Join-Path $root 'boom-runtime.dll'))}
$binding=@($programs['parallelStatic'].monitor_methods|Where-Object method -eq 'parallelStatic')[0]
[BoomMonitorProbe]::ClassLock($programs['parallelStatic'].compilation.dll,$binding.mirror_type)
$rejections=0
foreach($method in @('unsupportedWait','unsupportedBlock')){$destination=Join-Path $root ('reject-'+$method);& $Boom @argsList --method $method --output $destination 2>&1|Out-Null;if($LASTEXITCODE -eq 0 -or (Test-Path $destination)){throw 'Unsupported monitor/wait/handler execution accepted'};$rejections++}
$without=@('compile-program','--entry-class','dev/boom/monitors/MonitorEntry','--method','staticEntry','--output',(Join-Path $root 'reject-unverified'))
foreach($file in $files){$without+=@('--class-file',$file.FullName)}
& $Boom @without 2>&1|Out-Null;if($LASTEXITCODE -eq 0 -or (Test-Path (Join-Path $root 'reject-unverified'))){throw 'Unverified synchronized program accepted'};$rejections++
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $compilerSha){throw 'Monitor compiler changed during test'}
$report=[ordered]@{backend='boom-monitors-program-v18-masm-x64';compiler_sha256=$compilerSha;runtime_language='assembly';heap_monitor_capability=1;compiled_entries=$methods.Count;differential_cases=$cases.Count;native_executions=($cases.Count*2);multicore_records=(8195*6);workers=8;native_abi_contended_updates=8192;node_reuse_acquisitions=10000;reentrant_monitors=$true;distinct_object_monitors=$true;static_class_mirror_identity=$true;release_on_context_exception=$true;original_jdk_ByteArrayInputStream=$true;idle_monitor_nodes_reclaimed=$true;collection_refused_with_outstanding_monitors=$true;negative_checks=$rejections;monitor_bytecodes=$false;java_wait_notify_interrupt=$false;automatic_gc=$false;complete_java_memory_model=$false;passed=$true;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 8;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-monitor-program.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
