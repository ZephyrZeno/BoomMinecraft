param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/unsafe-bootstrap-tests/'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root classes
[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
foreach($file in $inputs.java.runtime_files){if((Get-FileHash $file.path).Hash.ToLowerInvariant() -ne $file.digest.sha256){throw 'Unsafe JVM oracle differs from lock'}}
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) -source 21 -target 21 --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/unsafe/LongAtomic.java java/reference/UnsafeBootstrapReference.java
if($LASTEXITCODE -ne 0){throw 'Unsafe fixture javac failed'}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('--add-exports','java.base/jdk.internal.misc=ALL-UNNAMED','-Xmx128m','-cp',$classes,'UnsafeBootstrapReference',(Join-Path $root oracle.bin))){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$java=[Diagnostics.Process]::new();$java.StartInfo=$info
try{if(-not $java.Start()){throw 'Unsafe oracle failed to start'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.WaitForExit(30000)){throw 'Unsafe oracle timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}}finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
if((Get-Item (Join-Path $root oracle.bin)).Length -ne 49152){throw 'Unsafe oracle record count differs'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
function Compile([string]$name,[string]$owner,[string]$method,[string]$descriptor,[string]$fixture=''){
    $output=Join-Path $root $name
    $compileArgs=if($fixture){@('compile-program','--class-file',$fixture,'--metadata-lock',$MetadataLock)}else{@('compile-locked-program','--lock',$MetadataLock)}
    & $Boom @compileArgs --jdk-base $JdkBase --entry-class $owner --method $method --descriptor $descriptor --output $output --assemble > (Join-Path $root "$name-compile.json") 2> (Join-Path $root "$name-compile.err")
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root "$name-compile.err") -Tail 10;throw "Unsafe $name compilation failed"}
    & D:/Dev/Python312/python.exe scripts/verify-unsafe-bootstrap-contract.py (Join-Path $output program.json) >> (Join-Path $root source-contract-checks.jsonl)
    if($LASTEXITCODE -ne 0){throw 'Independent Unsafe source contract check failed'}
    $p=Get-Content (Join-Path $output program.json) -Raw|ConvertFrom-Json
    if($p.full_game_ready -or ($p.schema -notin @(52,53,72)) -or $p.unsafe_bootstrap.full_unsafe_coverage -or $p.unsafe_bootstrap.executable_native_declarations -ne 12 -or -not $p.unsafe_bootstrap.int_array_operations -or $p.unsafe_bootstrap.long_array_and_thread_counter_only -or $p.unsafe_bootstrap.origin.sha256 -ne $base.classes.'jdk.internal.misc.Unsafe'.sha256 -or $p.unsafe_bootstrap.constants_origin.sha256 -ne $base.classes.'jdk.internal.misc.UnsafeConstants'.sha256){throw 'Unsafe capability/source scope differs'}
    return $p
}
$init=Compile init jdk/internal/misc/Unsafe getUnsafe '()Ljdk/internal/misc/Unsafe;'
$atomic=Compile atomic dev/boom/unsafe/LongAtomic apply '([JIJJI)J' (Join-Path $classes dev/boom/unsafe/LongAtomic.class)
$ids=Compile ids 'java/lang/Thread$ThreadIdentifiers' next '()J'
if(@($atomic.symbols|Where-Object {$_.class_name -eq 'jdk/internal/misc/Unsafe' -and $_.method -in @('getAndAddLong','weakCompareAndSetLong')}).Count -ne 2){throw 'Unsafe atomic Java loop was not retained'}
if(@($ids.symbols|Where-Object {$_.class_name -eq 'java/lang/Thread$ThreadIdentifiers' -and $_.method -in @('next','<clinit>')}).Count -ne 2 -or -not $ids.thread_natives){throw 'Original ThreadIdentifiers code was not compiled'}
$owner=@($init.classes|Where-Object name -eq jdk/internal/misc/Unsafe)[0]
$constants=@($init.classes|Where-Object name -eq jdk/internal/misc/UnsafeConstants)[0]
[uint32[]]$fields=@(foreach($suffix in @('BASE_OFFSET','INDEX_SCALE')){foreach($kind in @('BOOLEAN','BYTE','SHORT','CHAR','INT','LONG','FLOAT','DOUBLE','OBJECT')){[uint32]@($owner.fields|Where-Object name -eq "ARRAY_${kind}_${suffix}")[0].index}})+@([uint32]@($owner.fields|Where-Object name -eq ADDRESS_SIZE)[0].index)
[uint32[]]$vmFields=@(foreach($name in @('ADDRESS_SIZE0','PAGE_SIZE','BIG_ENDIAN','UNALIGNED_ACCESS','DATA_CACHE_LINE_FLUSH_SIZE')){[uint32]@($constants.fields|Where-Object name -eq $name)[0].index})
Add-Type -Path tests/host/UnsafeBootstrapProbe.cs
[BoomUnsafeBootstrapProbe]::Initialize($init.compilation.dll,(Join-Path $root boom-runtime.dll),[uint32]$owner.id,[uint32]$constants.id,$fields,$vmFields)
$atomicOwner=@($atomic.classes|Where-Object name -eq jdk/internal/misc/Unsafe)[0]
[BoomUnsafeBootstrapProbe]::Atomics($atomic.compilation.dll,(Join-Path $root boom-runtime.dll),(Join-Path $root oracle.bin),[uint32]$atomicOwner.id,[uint32]@($atomicOwner.fields|Where-Object name -eq theUnsafe)[0].index)
[BoomUnsafeBootstrapProbe]::ThreadIds($ids.compilation.dll,(Join-Path $root boom-runtime.dll))
& D:/Dev/Python312/python.exe scripts/make-unsafe-fixture.py $classes
if($LASTEXITCODE -ne 0){throw 'Unsafe private fixture generation failed'}
$reason=(& $Boom compile-program --class-file (Join-Path $classes dev/boom/unsafe/BadRegistration.class) --entry-class dev/boom/unsafe/BadRegistration --method run --descriptor '()V' --metadata-lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root private-call) --assemble 2>&1|ForEach-Object ToString)-join "`n"
if($LASTEXITCODE -eq 0 -or $reason -notmatch 'Unsafe private native requires its original caller'){throw 'Application called private Unsafe registrar'}
$info.ArgumentList.Clear()
foreach($arg in @('--add-exports','java.base/jdk.internal.misc=ALL-UNNAMED','-Xmx128m','-cp',$classes,'UnsafeBootstrapReference','bad')){$info.ArgumentList.Add($arg)}
$java=[Diagnostics.Process]::new();$java.StartInfo=$info
try{if(-not $java.Start()){throw 'Unsafe private JVM check failed to start'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.WaitForExit(30000)){throw 'Unsafe private JVM check timed out'};if($java.ExitCode -eq 0 -or $stderr.GetAwaiter().GetResult() -notmatch 'IllegalAccessError'){throw 'Unsafe private JVM access check differs'}}finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
$direct=(& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class jdk/internal/misc/Unsafe --method getLongVolatile --descriptor '(Ljava/lang/Object;J)J' --output (Join-Path $root direct-native) --assemble 2>&1|ForEach-Object ToString)-join "`n"
if($LASTEXITCODE -eq 0 -or $direct -notmatch 'Unsafe native entry cannot bypass original class initialization'){throw 'Direct Unsafe native entry skipped initialization'}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Unsafe compiler changed during verification'}
$sources=[ordered]@{}
foreach($path in @('src/compiler/unsafe_bootstrap.rs','native/runtime/unsafe_bootstrap.asm','scripts/Test-UnsafeBootstrap.ps1','scripts/verify-unsafe-bootstrap-contract.py','scripts/make-unsafe-fixture.py','tests/host/UnsafeBootstrapProbe.cs','java/subset/dev/boom/unsafe/LongAtomic.java','java/reference/UnsafeBootstrapReference.java')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_entries=3;original_Unsafe_and_UnsafeConstants_initializers_executed=$true;original_Unsafe_constructor_and_getUnsafe_executed=$true;original_getAndAddLong_and_weak_CAS_executed=$true;original_ThreadIdentifiers_initializer_and_next_executed=$true;executable_native_declarations=12;executable_operations=13;full_fence_supported=$true;full_unsafe_coverage=$false;long_array_and_thread_counter_only=$false;int_array_operations=$true;independent_classfile_contract_checks=3;cold_singleton_workers=8;cold_singleton_records=6147;original_array_layout_fields_checked=19;VM_constants_checked=5;JVM_atomic_cases=1024;native_JVM_differential_calls=2048;atomic_workers=8;contended_atomic_additions=6147;atomic_additions_allocate_guest_memory=$false;source_Thread_ID_workers=8;source_Thread_ID_records=6147;source_and_VM_share_ID_counter=$true;full_heap_zero_allocation_calls=8193;GC_static_and_array_root_graph_checked=$true;arbitrary_addresses_foreign_heaps_bad_offsets_and_pending_context_checked=$true;original_Thread_constructor_run_start_exit_executed=$false;automatic_gc=$false;System_boot_phases_completed=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;oracle_sha256=(Get-FileHash (Join-Path $root oracle.bin)).Hash.ToLowerInvariant();sources=$sources;run_directory=$root}
$report['original_native_declarations']=$init.unsafe_bootstrap.native_declarations
$report['private_registration_rejected_by_AOT_and_JVM']=$true
$report['direct_native_entry_cannot_bypass_initializer']=$true
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText('.boom/latest-unsafe-bootstrap-test.txt',$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
exit 0
