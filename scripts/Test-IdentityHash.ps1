param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='',[string]$JdkModules='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
if(-not $JdkModules){$JdkModules=Join-Path ((Get-Content .boom/latest-server-jdk-modules.txt -Raw).Trim()) 'jdk-modules.json'}
$root=Join-Path (Get-Location) ('.boom/identity-hash-tests/'+[guid]::NewGuid().ToString('N'));$classes=Join-Path $root classes;[IO.Directory]::CreateDirectory($classes)|Out-Null
[IO.File]::WriteAllText('.boom/current-identity-hash-test.txt',$root,[Text.UTF8Encoding]::new($false))
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) 'javac.exe') --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/identity/HashProgram.java java/subset/dev/boom/identity/HashExceptions.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'Hash reference javac failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root > (Join-Path $root runtime-build.log) 2>&1
& scripts/Build-FpProbe.ps1 -Output $root > (Join-Path $root fp-build.log) 2>&1
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/IdentityHashProbe.cs
$core=@('plain','overridden','superHash','interfaceHash','arrays','directArray','stringHash','opaque','directOpaque','nullIdentity','hot','parallel','objects');$errors=@('nullReceiver','nullArray','nullOpaque','throwing');$methods=@($core)+@($errors);$programs=@{}
foreach($method in $methods){
    $owner=if($method -in $errors){'HashExceptions'}else{'HashProgram'};$descriptor=if($method -eq 'objects'){'(I)Ljava/lang/Object;'}else{'(I)I'}
    $a=@();foreach($f in Get-ChildItem (Join-Path $classes dev/boom/identity) -Filter ($owner+'*.class')){$a+=@('--class-file',$f.FullName)}
    & $Boom compile-program @a --entry-class ('dev/boom/identity/'+$owner) --method $method --descriptor $descriptor --metadata-lock $MetadataLock --jdk-base $JdkBase --jdk-modules $JdkModules --output (Join-Path $root $method) --assemble > (Join-Path $root ($method+'-compile.json')) 2> (Join-Path $root ($method+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'-compile.err')) -Tail 15;throw "Hash compilation failed: $method"}
    $p=Get-Content (Join-Path $root ($method+'/program.json')) -Raw|ConvertFrom-Json
    if($p.schema -ne 35 -or $p.backend -ne 'boom-identity-hash-program-v35-masm-x64' -or $p.identity_hashes.Count -eq 0){throw 'Identity hash source profile missing'}
    foreach($b in $p.identity_hashes){$provider=if($b.kind -eq 'SystemIdentity'){'java.lang.System'}else{'java.lang.Object'};if($b.abi -ne 1 -or $b.nonmoving_heap_abi -ne 1 -or $b.origin.sha256 -ne $base.classes.$provider.sha256 -or $b.native_source_sha256 -ne (Get-FileHash native/runtime/identity_hash.asm).Hash.ToLowerInvariant() -or $b.heap_source_sha256 -ne (Get-FileHash native/runtime/heap.asm).Hash.ToLowerInvariant()){throw 'Identity hash source or nonmoving heap proof changed'}}
    foreach($site in $p.interface_dispatch){if(($null -ne $site.array_identity_hash -or @($site.rows|Where-Object runtime_identity_hash).Count) -and $p.interface_dispatch_abi -ne 3){throw 'Native hash dispatch ABI missing'}}
    $programs[$method]=$p;Write-Output "Compiled source-proven identity/hash dispatch: $method"
}
function Java([string]$text){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($a in @('-Xmx128m','-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($a)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $java=[Diagnostics.Process]::new();$java.StartInfo=$info
    try{if(-not $java.Start()){throw 'Hash JVM reference failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.StandardInput.WriteAsync($text).Wait(15000)){throw 'Hash JVM input stalled'};$java.StandardInput.Close();if(-not $java.WaitForExit(30000)){throw 'Hash JVM reference timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};return $stdout.GetAwaiter().GetResult()}
    finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
}
$values=[Collections.Generic.List[string]]::new();foreach($i in 0..127){$values.Add($i.ToString('x'))};foreach($v in @(128,255,65535,2147483647,2147483648,4294967295,2147483649,2147418112)){$values.Add(([uint32]$v).ToString('x'))}
[uint64]$seed=0x12345678;for($i=0;$i -lt 96;$i++){$seed=($seed*1664525+1013904223) -band 0xffffffffL;$values.Add($seed.ToString('x'))}
$numeric=@($methods|Where-Object {$_ -ne 'objects'})
$lines=@(foreach($method in $numeric){$owner=if($method -in $errors){'HashExceptions'}else{'HashProgram'};foreach($v in $values){'dev.boom.identity.'+$owner+' '+$method+' (I)I '+$v}})
$expected=@((Java (($lines -join "`n")+"`n")).Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {$_.Trim()})
if($expected.Count -ne $lines.Count){throw 'Hash JVM reference count mismatch'}
$index=0
foreach($method in $numeric){$actual=[BoomNumericProbe]::Run($programs[$method].compilation.dll,(Join-Path $root fpstate.dll),$values.ToArray(),'I',$true);foreach($v in $actual){if($v -ne $expected[$index]){throw "Identity JVM relation mismatch: $method at $index, native=$v, JVM=$($expected[$index])"};$index++};Write-Output "Validated identity relations, dispatch and source errors: $method"}
[BoomIdentityHashProbe]::ObjectsAndGC($programs.objects.compilation.dll)
[BoomIdentityHashProbe]::FullHeapNoAllocation($programs.hot.compilation.dll,(Join-Path $root boom-runtime.dll))
$parallelLines=@(foreach($i in 0..2048){'dev.boom.identity.HashProgram parallel (I)I '+$i.ToString('x')})
$parallelExpected=@((Java (($parallelLines -join "`n")+"`n")).Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {[BitConverter]::ToInt32([BitConverter]::GetBytes([Convert]::ToUInt32($_.Trim().Substring(2),16)),0)})
$p=$programs.parallel;$owner=@($p.classes|Where-Object name -eq 'dev/boom/identity/HashProgram')[0];$sync=@($owner.fields|Where-Object name -eq 'SYNCHRONIZED')[0];$layout=@($p.object_layouts|Where-Object class_name -eq 'dev/boom/identity/HashProgram$Sync')[0];$calls=@($layout.layout.fields|Where-Object name -eq 'calls')[0]
[BoomIdentityHashProbe]::Parallel($p.compilation.dll,(Join-Path $root boom-runtime.dll),[int[]]$parallelExpected,$owner.id,$sync.index,$calls.offset)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Hash compiler changed during run'}
$sources=[ordered]@{};foreach($path in @('native/runtime/identity_hash.asm','native/runtime/heap.asm','java/subset/dev/boom/identity/HashProgram.java','java/subset/dev/boom/identity/HashExceptions.java','tests/host/IdentityHashProbe.cs','scripts/Test-IdentityHash.ps1')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{backend='boom-identity-hash-program-v35-masm-x64';compiler_sha256=$sha;runtime_language='assembly';compiled_entries=$methods.Count;JVM_relation_cases=$lines.Count;native_differential_executions=($lines.Count*2);raw_hash_values_compared_across_VMs=$false;Object_default_and_System_identity_agree=$true;Java_overrides_and_invokespecial_preserved=$true;String_content_hash_preserved=$true;arrays_use_runtime_descriptor_assignability=$true;direct_primitive_and_reference_array_calls=$true;direct_VM_owned_receiver_calls=$true;Class_Module_and_ModuleLayer_hashes=$true;null_identity_zero_and_virtual_NPE=$true;original_Java_override_exception_caught=$true;live_hashes_stable_across_quiescent_GC=$true;native_no_allocation_calls=8193;full_heap_source_no_allocation_calls=8193;aligned_objects_distribution_samples=1024;minimum_distinct_sample_hashes=1000;workers=8;multicore_records=6147;synchronized_override_calls=6147;identity_calls_do_not_invoke_overrides=$true;nonmoving_heap_abi=1;automatic_gc=$false;sources=$sources;System_properties_bootstrap_complete=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 7
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-identity-hash-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
