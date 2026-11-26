param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/vm-registration-tests/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-vm-registration-test.txt',$root,[Text.UTF8Encoding]::new($false))
$classes=Join-Path $root classes;$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
$java=$inputs.java.executable;$javac=Join-Path (Split-Path $java) javac.exe
& $javac -source 21 -target 21 --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -g -proc:none -d $classes java/subset/dev/boom/vm/VmRegistrationProgram.java java/subset/dev/boom/vm/VmRegistrationReference.java
if($LASTEXITCODE -ne 0){throw 'VM reference javac failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
& scripts/Build-FpProbe.ps1 -Output $root *> (Join-Path $root fp-build.log)
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/CloneProbe.cs
Add-Type -Path tests/host/VmRegistrationProbe.cs
$programs=@{}
foreach($method in @('state','memory','adjustment')){
    $desc=switch($method){state{'(I)I'};memory{'(I)J'};default{'(J)J'}};$out=Join-Path $root $method
    & $Boom compile-program --class-file (Join-Path $classes dev/boom/vm/VmRegistrationProgram.class) --entry-class dev/boom/vm/VmRegistrationProgram --method $method --descriptor $desc --metadata-lock $MetadataLock --jdk-base $JdkBase --output $out --assemble > (Join-Path $root ($method+'-compile.json')) 2> (Join-Path $root ($method+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'-compile.err')) -Tail 12;throw "VM registration compile failed: $method"}
    $p=Get-Content (Join-Path $out program.json) -Raw|ConvertFrom-Json
    if($p.schema -ne 43 -or $p.vm_registration.Count -eq 0 -or $p.full_game_ready -or @($p.symbols|Where-Object {$_.class_name -eq 'jdk/internal/misc/VM' -and $_.method -eq '<clinit>'}).Count -ne 1){throw 'Original VM initializer/binding missing'}
    foreach($b in $p.vm_registration){if($b.abi -ne 1 -or $b.origin.sha256 -ne $base.classes.'jdk.internal.misc.VM'.sha256 -or $b.origin.loader -ne 'bootstrap' -or $b.vm_boot_level_changed -or $b.registered_name -ne 'getNanoTimeAdjustment' -or $b.registered_descriptor -ne '(J)J' -or $b.native_source_sha256 -ne (Get-FileHash native/runtime/vm_registration.asm).Hash.ToLowerInvariant()){throw 'VM original native contract changed'};if($b.operation -eq 'Initialize' -and ($b.caller.sha256 -ne $b.origin.sha256 -or $b.caller.loader -ne 'bootstrap')){throw 'Private VM registration origin differs'}}
    $programs[$method]=$p
    Write-Output "Compiled original VM initializer/native: $method"|Out-Host
}
[BoomVmRegistrationProbe]::Native($programs.state.compilation.dll)
$arithmetic=[BoomVmRegistrationProbe]::ArithmeticCases($programs.adjustment.compilation.dll)
if($arithmetic -ne 20126){throw 'Arithmetic test scope changed'}
[BoomVmRegistrationProbe]::Adjustment($programs.adjustment.compilation.dll)
[string[]]$small=@(0..127|ForEach-Object{$_.ToString('x8')})
$states=[BoomNumericProbe]::Run($programs.state.compilation.dll,(Join-Path $root fpstate.dll),$small,'I',$true)
$memory=[BoomNumericProbe]::Run($programs.memory.compilation.dll,(Join-Path $root fpstate.dll),$small,'J',$true)
if($states.Count -ne 128 -or @($states|Where-Object {$_ -cne 'v 0000000000000000'}).Count -or $memory.Count -ne 128 -or @($memory|Where-Object {$_ -cne 'v 0000000004000000'}).Count){throw 'Native VM pre-System phase defaults changed'}
[BoomCloneProbe]::Parallel($programs.state.compilation.dll,(Join-Path $root boom-runtime.dll),[int[]]::new(2049))
function Java([string[]]$cases){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$java;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('--add-exports','java.base/jdk.internal.misc=ALL-UNNAMED','-cp',$classes,'dev.boom.vm.VmRegistrationReference','adjustment')){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $p=[Diagnostics.Process]::new();$p.StartInfo=$info
    try{if(-not $p.Start()){throw 'VM JVM reference failed'};$stdout=$p.StandardOutput.ReadToEndAsync();$stderr=$p.StandardError.ReadToEndAsync();if(-not $p.StandardInput.WriteAsync(($cases -join "`n")+"`n").Wait(15000)){throw 'VM JVM input stalled'};$p.StandardInput.Close();if(-not $p.WaitForExit(30000)){throw 'VM JVM reference timed out'};if($p.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};return @($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})}finally{if(-not $p.HasExited){$p.Kill($true);$p.WaitForExit()};$p.Dispose()}
}
$random=[Random]::new(43043);$bytes=[byte[]]::new(8);$far=[Collections.Generic.List[string]]::new()
foreach($value in @('8000000000000000','7fffffffffffffff','0000010000000000','ffffff0000000000')){$far.Add($value)}
while($far.Count -lt 512){$random.NextBytes($bytes);$v=[BitConverter]::ToUInt64($bytes,0);$v=$v -bor [uint64]1099511627776;$far.Add($v.ToString('x16'))}
$native=[BoomNumericProbe]::Run($programs.adjustment.compilation.dll,(Join-Path $root fpstate.dll),$far.ToArray(),'J',$true)
$expected=Java $far.ToArray()
if($native.Count -ne 512 -or $expected.Count -ne 512 -or ($native -join '|') -cne ($expected -join '|') -or @($native|Where-Object {$_ -cne 'v ffffffffffffffff'}).Count){throw 'VM offset sentinel/JVM mismatch'}
[IO.File]::WriteAllLines((Join-Path $root far-native.txt),[string[]]$native);[IO.File]::WriteAllLines((Join-Path $root far-reference.txt),[string[]]$expected)
$before=[BoomVmRegistrationProbe]::NowFileTime();$clock=Java ([string[]]::new(32)|ForEach-Object{'0'});$after=[BoomVmRegistrationProbe]::NowFileTime()
[BoomVmRegistrationProbe]::ReferenceClock([string[]]$clock,$before,$after)

# A minimal valid classfile calls the private bootstrap native from another class.
$stream=[IO.MemoryStream]::new();$writer=[IO.BinaryWriter]::new($stream)
function U1([int]$v){$writer.Write([byte]$v)}
function U2([int]$v){U1 (($v -shr 8) -band 255);U1 ($v -band 255)}
function U4([uint32]$v){U2 (($v -shr 16) -band 65535);U2 ($v -band 65535)}
function Utf([string]$v){$data=[Text.Encoding]::UTF8.GetBytes($v);U1 1;U2 $data.Length;$writer.Write($data)}
U4 ([Convert]::ToUInt32('cafebabe',16));U2 0;U2 65;U2 13
Utf 'dev/boom/vm/ForgedInitialize';U1 7;U2 1;Utf 'java/lang/Object';U1 7;U2 3;Utf 'run';Utf '()V';Utf 'Code';Utf 'jdk/internal/misc/VM';U1 7;U2 8;Utf 'initialize';U1 12;U2 10;U2 6;U1 10;U2 9;U2 11
U2 0x21;U2 2;U2 4;U2 0;U2 0;U2 1;U2 9;U2 5;U2 6;U2 1;U2 7;U4 16;U2 0;U2 0;U4 4;U1 0xb8;U2 12;U1 0xb1;U2 0;U2 0;U2 0
$badClass=Join-Path $classes dev/boom/vm/ForgedInitialize.class;[IO.File]::WriteAllBytes($badClass,$stream.ToArray());$writer.Dispose();$stream.Dispose()
$badOut=Join-Path $root rejected-private
$reason=(& $Boom compile-program --class-file $badClass --entry-class dev/boom/vm/ForgedInitialize --method run --descriptor '()V' --metadata-lock $MetadataLock --jdk-base $JdkBase --output $badOut --assemble 2>&1|ForEach-Object ToString)-join "`n"
if($LASTEXITCODE -eq 0 -or $reason -notmatch 'VM.initialize is private' -or (Test-Path (Join-Path $badOut program.json))){throw 'Private bootstrap VM registration accepted an application caller'}
$jvm=(& $java --add-exports java.base/jdk.internal.misc=ALL-UNNAMED -cp $classes dev.boom.vm.VmRegistrationReference forged 2>&1|ForEach-Object ToString)-join "`n"
if($LASTEXITCODE -eq 0 -or $jvm -notmatch 'IllegalAccessError'){throw 'JVM private native rejection differs'}
[IO.File]::WriteAllText((Join-Path $root private-aot.txt),$reason);[IO.File]::WriteAllText((Join-Path $root private-jvm.txt),$jvm)
$inspect=Join-Path $root bridges;$inspectArgs=@('inspect-jdk-bridges','--lock',$MetadataLock,'--jdk-base',$JdkBase,'--output',$inspect)
foreach($id in 1..10){$inspectArgs+=@('--bridge-id',$id)}
& $Boom @inspectArgs > (Join-Path $root bridges-inspect.json)
if($LASTEXITCODE -ne 0){throw 'JDK bridge export failed'}
& D:\Dev\Python312\python.exe scripts/verify-jdk-bridges.py (Join-Path $inspect inspection.json) > (Join-Path $root bridges-raw-check.json)
if($LASTEXITCODE -ne 0){throw 'Independent JDK Code/attribute verification failed'}
$bridge=Get-Content (Join-Path $root bridges-raw-check.json) -Raw|ConvertFrom-Json
if($bridge.bridges -ne 10 -or -not $bridge.passed -or $bridge.execution_complete){throw 'Bridge verification scope changed'}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'VM compiler changed during verification'}
$hashes=[ordered]@{}
foreach($path in @('native/runtime/vm_registration.asm','src/compiler/vm_registration.rs','src/compiler/jdk_bridges.rs','tests/host/VmRegistrationProbe.cs','java/subset/dev/boom/vm/VmRegistrationProgram.java','java/subset/dev/boom/vm/VmRegistrationReference.java','scripts/Test-VmRegistration.ps1','scripts/verify-jdk-bridges.py')){$hashes[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_entries=3;original_VM_initializer_and_queries_executed=$true;original_VM_boot_level=0;VM_boot_level_compared_with_host_JVM=$false;System_boot_phases_completed=$false;exact_arithmetic_vectors=$arithmetic;JVM_far_offset_differential_cases=512;native_far_offset_calls=1024;JVM_UTC_bracket_samples=$clock.Count;native_UTC_bracket_samples=1024;registration_no_allocation_calls=8193;workers=8;multicore_records=6147;private_call_rejected_by_AOT_and_JVM=$true;pending_context_and_metadata_gates=$true;quiescent_GC_static_lock_retained=$true;bridges_raw_Code_and_all_method_attributes_checked=10;String_format_original_bridges_generated=$true;String_format_execution_complete=$false;automatic_gc=$false;full_game_ready=$false;passed=$true;sources=$hashes;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 7
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-vm-registration-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
