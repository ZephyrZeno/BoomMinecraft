param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/hex-string-tests/'+[guid]::NewGuid().ToString('N'));$classes=Join-Path $root classes;[IO.Directory]::CreateDirectory($classes)|Out-Null
[IO.File]::WriteAllText('.boom/current-hex-string-test.txt',$root,[Text.UTF8Encoding]::new($false))
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/hex/HexProgram.java java/subset/dev/boom/hex/HexReference.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'Hex javac reference failed'}
& $inputs.java.executable -cp $classes dev.boom.hex.HexReference (Join-Path $root oracle.bin)
if($LASTEXITCODE -ne 0){throw 'Hex JVM raw reference failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root > (Join-Path $root runtime-build.log) 2>&1
& scripts/Build-FpProbe.ps1 -Output $root > (Join-Path $root fp-build.log) 2>&1
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/HexStringProbe.cs
$methods=@('intValue','longValue','intRelations','longRelations','parallel','allocation','fullHeap','fullHeapLong');$programs=@{}
foreach($method in $methods){
    $arg=if($method -in @('longValue','longRelations','fullHeapLong')){'J'}else{'I'};$ret=if($method -in @('intValue','longValue')){'Ljava/lang/String;'}else{'I'};$descriptor='('+$arg+')'+$ret
    & $Boom compile-program --class-file (Join-Path $classes dev/boom/hex/HexProgram.class) --entry-class dev/boom/hex/HexProgram --method $method --descriptor $descriptor --metadata-lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root $method) --assemble > (Join-Path $root ($method+'-compile.json')) 2> (Join-Path $root ($method+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'-compile.err')) -Tail 15;throw "Hex compile failed: $method"}
    $p=Get-Content (Join-Path $root ($method+'/program.json')) -Raw|ConvertFrom-Json
    if($p.schema -ne 36 -or $p.backend -ne 'boom-hex-string-program-v36-masm-x64' -or $p.hex_strings.Count -eq 0){throw 'Hex profile/source proof missing'}
    foreach($b in $p.hex_strings){$owner=if($b.kind -eq 'Int'){'java.lang.Integer'}else{'java.lang.Long'};if($b.abi -ne 1 -or $b.origin.sha256 -ne $base.classes.$owner.sha256 -or $b.native_source_sha256 -ne (Get-FileHash native/runtime/hex_strings.asm).Hash.ToLowerInvariant() -or @($p.symbols|Where-Object {$_.class_name -eq $owner.Replace('.','/') -and $_.method -eq '<clinit>'}).Count -ne 1){throw 'Hex initializer/native source contract changed'}}
    $programs[$method]=$p;Write-Output "Compiled source-proven hex conversion: $method"
}
$raw=[BoomHexStringProbe]::RawOutputs($programs.intValue.compilation.dll,$programs.longValue.compilation.dll,(Join-Path $root oracle.bin))
if($raw[0] -ne 4226 -or $raw[1] -ne 4354){throw 'Raw hex oracle scope changed'}
function Java([string]$text){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($a in @('-Xmx128m','-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($a)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $java=[Diagnostics.Process]::new();$java.StartInfo=$info
    try{if(-not $java.Start()){throw 'Hex JVM reference failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.StandardInput.WriteAsync($text).Wait(15000)){throw 'Hex JVM input stalled'};$java.StandardInput.Close();if(-not $java.WaitForExit(30000)){throw 'Hex JVM reference timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};return $stdout.GetAwaiter().GetResult()}
    finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
}
$ints=[Collections.Generic.List[string]]::new();foreach($v in @(0,1,2,7,15,16,17,127,128,255,256,65535,2147483647,2147483648,4294967295)){$ints.Add(([uint32]$v).ToString('x'))};[uint64]$seed=0x12345678
for($i=0;$i -lt 128;$i++){$seed=($seed*1664525+1013904223) -band 0xffffffffL;$ints.Add($seed.ToString('x'))}
$longs=[Collections.Generic.List[string]]::new();foreach($v in @('0','1','f','10','100000000','7fffffffffffffff','8000000000000000','ffffffffffffffff','ffffffff00000000','100000001')){$longs.Add($v)}
for($i=0;$i -lt 128;$i++){$seed=($seed*1664525+1013904223) -band 0xffffffffL;$hi=$seed;$seed=($seed*1664525+1013904223) -band 0xffffffffL;$longs.Add($hi.ToString('x8')+$seed.ToString('x8'))}
$numeric=@($methods|Where-Object {$_ -notin @('intValue','longValue')});$cases=@{}
foreach($method in $numeric){$cases[$method]=if($method -in @('longRelations','fullHeapLong')){$longs}else{$ints}}
$lines=@(foreach($method in $numeric){foreach($v in $cases[$method]){'dev.boom.hex.HexProgram '+$method+' '+$(if($method -in @('longRelations','fullHeapLong')){'(J)I'}else{'(I)I'})+' '+$v}})
$expected=@((Java (($lines -join "`n")+"`n")).Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {$_.Trim()});if($expected.Count -ne $lines.Count){throw 'Hex relation oracle count changed'}
$index=0;foreach($method in $numeric){$actual=[BoomNumericProbe]::Run($programs[$method].compilation.dll,(Join-Path $root fpstate.dll),[string[]]$cases[$method],'I',$true);foreach($v in $actual){if($v -ne $expected[$index]){throw "Hex JVM relation mismatch: $method at $index"};$index++};Write-Output "Validated JVM hex relations and native GC: $method"}
[BoomHexStringProbe]::AllocationAndFailures($programs.intValue.compilation.dll,(Join-Path $root boom-runtime.dll))
[BoomHexStringProbe]::FullHeap($programs.fullHeap.compilation.dll,(Join-Path $root boom-runtime.dll),32)
[BoomHexStringProbe]::FullHeap($programs.fullHeapLong.compilation.dll,(Join-Path $root boom-runtime.dll),64)
$parallelLines=@(foreach($i in 0..2048){'dev.boom.hex.HexProgram parallel (I)I '+$i.ToString('x')});$parallelExpected=@((Java (($parallelLines -join "`n")+"`n")).Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {[BitConverter]::ToInt32([BitConverter]::GetBytes([Convert]::ToUInt32($_.Trim().Substring(2),16)),0)})
[BoomHexStringProbe]::Parallel($programs.parallel.compilation.dll,(Join-Path $root boom-runtime.dll),[int[]]$parallelExpected)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Hex compiler changed during run'}
$sources=[ordered]@{};foreach($path in @('native/runtime/hex_strings.asm','java/subset/dev/boom/hex/HexProgram.java','java/subset/dev/boom/hex/HexReference.java','tests/host/HexStringProbe.cs','scripts/Test-HexStrings.ps1')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{backend='boom-hex-string-program-v36-masm-x64';compiler_sha256=$sha;runtime_language='assembly';compiled_entries=$methods.Count;raw_UTF16_JVM_cases=($raw[0]+$raw[1]);int_raw_cases=$raw[0];long_raw_cases=$raw[1];numeric_JVM_relation_cases=$lines.Count;numeric_native_executions=($lines.Count*2);zero_signed_extremes_and_nibble_boundaries=$true;all_random_input_bits_preserved=$true;lowercase_no_leading_zero_UTF16=$true;fresh_String_and_independent_array=$true;original_Integer_Long_initializers_executed=$true;allocation_budget_calls=256;guest_allocations_per_warm_conversion=2;partial_allocation_OOM_and_recovery=$true;full_heap_OOM_catch_calls=256;workers=8;multicore_records=6147;metadata_and_width_gates=$true;pending_error_preserved=$true;automatic_gc=$false;sources=$sources;Object_toString_complete=$false;StringBuilder_complete=$false;System_properties_bootstrap_complete=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 7
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-hex-string-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
