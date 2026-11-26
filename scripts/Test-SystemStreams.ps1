param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='',[string]$JdkModules='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
if(-not $JdkModules){$JdkModules=Join-Path ((Get-Content .boom/latest-server-jdk-modules.txt -Raw).Trim()) jdk-modules.json}
$root=Join-Path (Get-Location) ('.boom/system-stream-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-system-stream-test.txt',$root,[Text.UTF8Encoding]::new($false))
$classes=Join-Path $root classes;$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes java/reference/SystemStreamsReference.java
if($LASTEXITCODE -ne 0){throw 'System stream oracle javac failed'}
function Java([string[]]$arguments){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('--add-opens','java.base/java.lang=ALL-UNNAMED','-Xmx128m','-cp',$classes,'SystemStreamsReference')+$arguments){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $java=[Diagnostics.Process]::new();$java.StartInfo=$info
    try{if(-not $java.Start()){throw 'System stream JVM oracle failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.WaitForExit(120000)){throw 'System stream JVM oracle timed out'};return @{code=$java.ExitCode;stdout=$stdout.GetAwaiter().GetResult();stderr=$stderr.GetAwaiter().GetResult()}}finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
}
$oracle=Join-Path $root streams.bin;$java=Java -arguments @($oracle);if($java.code -ne 0){throw $java.stderr}
$bytes=[IO.File]::ReadAllBytes($oracle);if($bytes.Length -ne 4096){throw 'System stream oracle size changed'}
[int[]]$expected=@(for($i=0;$i -lt 1024;$i++){([int]$bytes[$i*4] -shl 24)-bor([int]$bytes[$i*4+1] -shl 16)-bor([int]$bytes[$i*4+2] -shl 8)-bor[int]$bytes[$i*4+3]})
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
Add-Type -Path tests/host/SystemStreamsProbe.cs
$programs=@{}
foreach($op in 0..2){
    $name=@('setIn0','setOut0','setErr0')[$op];$desc=if($op -eq 0){'(Ljava/io/InputStream;)V'}else{'(Ljava/io/PrintStream;)V'};$out=Join-Path $root $name
    & $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class java/lang/System --method $name --descriptor $desc --output $out --assemble > (Join-Path $root ($name+'-compile.json')) 2> (Join-Path $root ($name+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($name+'-compile.err')) -Tail 14;throw "Original System native stream entry failed: $name"}
    $p=Get-Content (Join-Path $out program.json) -Raw|ConvertFrom-Json;$plan=$p.system_streams
    if($p.schema -ne 46 -or $p.system_startup -or $p.full_game_ready -or $plan.abi -ne 1 -or $plan.origin.sha256 -ne $base.classes.'java.lang.System'.sha256 -or $plan.slots.Count -ne 3 -or $plan.storage.Count -ne 2 -or $plan.completes_system_startup -or $plan.automatic_gc -or $plan.entry[1] -ne @('In','Out','Err')[$op]){throw 'System native setter original source/state contract changed'}
    foreach($s in $plan.storage){foreach($o in $s.origins){if($o.loader -ne 'bootstrap' -or $o.generated -or $o.sha256 -ne $base.classes.($o.binary_name).sha256){throw 'Stream physical storage source/ancestor changed'}}}
    foreach($pair in @(@('native_source_sha256','native/runtime/system_streams.asm'),@('heap_source_sha256','native/runtime/heap.asm'),@('runtime_types_source_sha256','native/runtime/runtime_types.asm'),@('types_source_sha256','native/runtime/types.asm'))){if($plan.($pair[0]) -ne (Get-FileHash $pair[1]).Hash.ToLowerInvariant()){throw 'Native setter dependency changed'}}
    $offset=($plan.storage[0].layout.fields|Where-Object {$_.name -eq 'buf' -and $_.descriptor -eq '[B'}).offset
    [BoomSystemStreamsProbe]::Run($p.compilation.dll,(Join-Path $root boom-runtime.dll),$op,$offset,$expected)
    $programs[$name]=$p;Write-Output "Validated original private $name entry, rooted references, full heap and cold/warm assembly workers"
}
& D:/Dev/Python312/python.exe scripts/make-system-stream-fixtures.py $classes;if($LASTEXITCODE -ne 0){throw 'System private access fixture generation failed'}
$rejected=@(foreach($bad in Get-Content (Join-Path $classes bad-system-streams.json) -Raw|ConvertFrom-Json){
    $out=Join-Path $root ('bad-'+$bad.method);$reason=(& $Boom compile-program --class-file $bad.path --entry-class $bad.name --method run --descriptor '()V' --metadata-lock $MetadataLock --jdk-base $JdkBase --output $out --assemble 2>&1|ForEach-Object ToString)-join "`n"
    if($LASTEXITCODE -eq 0 -or (Test-Path (Join-Path $out program.json)) -or $reason -notmatch 'private|startup phases'){throw 'Application private System call was accepted'}
    $java=Java -arguments @('bad',$bad.name.Replace('/','.'));if($java.code -eq 0 -or $java.stderr -notmatch 'IllegalAccessError'){throw 'JVM accepted forged private System caller'}
    [IO.File]::WriteAllText((Join-Path $root ($bad.method+'-private-aot.txt')),$reason);[IO.File]::WriteAllText((Join-Path $root ($bad.method+'-private-jvm.txt')),$java.stderr)
    [ordered]@{method=$bad.method;AOT_rejected=$true;JVM_rejected=$true}
})
$gates=@(foreach($entry in @(@('getProperties','()Ljava/util/Properties;'),@('setErr','(Ljava/io/PrintStream;)V'),@('initPhase2','(ZZ)I'),@('initPhase3','()V'))){
    $out=Join-Path $root ('gated-'+$entry[0]);$reason=(& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class java/lang/System --method $entry[0] --descriptor $entry[1] --output $out --assemble 2>&1|ForEach-Object ToString)-join "`n"
    if($LASTEXITCODE -eq 0 -or $reason -notmatch 'System Java startup phases 1/2/3' -or (Test-Path (Join-Path $out program.json))){throw 'System boot phase invocation leaked into application/later phase access'}
    [ordered]@{method=$entry[0];rejected=$true}
})
$phaseOut=Join-Path $root phase1;$phase=(& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --jdk-modules $JdkModules --entry-class java/lang/System --method initPhase1 --descriptor '()V' --output $phaseOut --assemble 2>&1|ForEach-Object ToString)-join "`n"
if($LASTEXITCODE -eq 0 -or $phase -notmatch 'Linking locked jdk/internal/misc/Signal.handle0' -or $phase -notmatch 'requires its own assembly runtime binding' -or (Test-Path (Join-Path $phaseOut program.json))){throw 'Original phase-one dependency frontier changed; inspect before recording'}
[IO.File]::WriteAllText((Join-Path $root phase1-frontier.txt),$phase,[Text.UTF8Encoding]::new($false))
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'System stream compiler changed during verification'}
$sources=[ordered]@{};foreach($path in @('src/compiler/system_streams.rs','src/compiler/system_startup.rs','native/runtime/system_streams.asm','tests/host/SystemStreamsProbe.cs','java/reference/SystemStreamsReference.java','scripts/Test-SystemStreams.ps1','scripts/make-system-stream-fixtures.py')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_entries=3;original_System_initializer_executed=$true;JVM_reference_sequences=1024;native_relation_checks=3072;VM_prepared_storage_only=$true;stream_constructors_and_IO_executed=$false;native_entry_argument_publication_calls=384;actual_static_root_cells_updated=$true;null_allowed_and_types_checked=$true;GC_shared_alias_and_overwritten_input_graph_checked=$true;metadata_foreign_heap_pending_and_uninitialized_class_gates=$true;full_heap_no_allocation_calls=24579;workers=8;cold_start_multicore_records=18441;warm_multicore_records=18441;private_calls_rejected=$rejected;application_and_later_phase_gates=$gates;phase1_invocation_only=$true;phase1_compilation_complete=$false;phase1_frontier=$phase;System_boot_phases_completed=$false;automatic_gc=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;oracle_sha256=(Get-FileHash $oracle).Hash.ToLowerInvariant();sources=$sources;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-system-stream-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
