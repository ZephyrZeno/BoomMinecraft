param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/string-prefix-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-string-prefix-test.txt',$root,[Text.UTF8Encoding]::new($false))
$classes=Join-Path $root classes;$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/prefix/PrefixProgram.java java/subset/dev/boom/prefix/PrefixReference.java
if($LASTEXITCODE -ne 0){throw 'Prefix JVM reference javac failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
& scripts/Build-FpProbe.ps1 -Output $root *> (Join-Path $root fp-build.log)
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/ReplaceProbe.cs
Add-Type -Path tests/host/PrefixProbe.cs
$programs=@{}
foreach($method in @('objects','offset','start','end','raw','dynamic','nullOrder','fullHeap','parallel')){
    $desc=switch($method){objects {'(I)Ljava/lang/String;'};offset {'(III)I'};raw {'(III)I'};start {'(II)I'};end {'(II)I'};default {'(I)I'}}
    $out=Join-Path $root $method
    & $Boom compile-program --class-file (Join-Path $classes dev/boom/prefix/PrefixProgram.class) --entry-class dev/boom/prefix/PrefixProgram --method $method --descriptor $desc --metadata-lock $MetadataLock --jdk-base $JdkBase --output $out --assemble > (Join-Path $root ($method+'-compile.json')) 2> (Join-Path $root ($method+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'-compile.err')) -Tail 12;throw "Prefix compilation failed: $method"}
    $p=Get-Content (Join-Path $out program.json) -Raw|ConvertFrom-Json
    if($p.schema -ne 47 -or $p.string_prefix.Count -eq 0 -or $p.full_game_ready){throw 'Prefix original source binding missing'}
    foreach($b in $p.string_prefix){if($b.abi -ne 1 -or $b.storage_abi -ne 3 -or $b.compact_strings -or $b.vector_bytes -ne 16 -or $b.origin.sha256 -ne $base.classes.'java.lang.String'.sha256 -or $b.arrays_support_origin.sha256 -ne $base.classes.'jdk.internal.util.ArraysSupport'.sha256 -or $b.utf16_origin.sha256 -ne $base.classes.'java.lang.StringUTF16'.sha256){throw 'Prefix source/storage/vector contract changed'};foreach($entry in @(@('native_source_sha256','native/runtime/string_prefix.asm'),@('string_source_sha256','native/runtime/strings.asm'),@('heap_source_sha256','native/runtime/heap.asm'))){if($b.($entry[0]) -ne (Get-FileHash $entry[1]).Hash.ToLowerInvariant()){throw 'Prefix native source proof changed'}}}
    if($method -eq 'start' -and @($p.jdk_bridges|Where-Object kind -eq StartsWith).Count -ne 1){throw 'Original startsWith wrapper missing'}
    if($method -eq 'end' -and @($p.jdk_bridges|Where-Object kind -eq EndsWith).Count -ne 1){throw 'Original endsWith wrapper missing'}
    $programs[$method]=$p;Write-Output "Compiled prefix helper and original Java wrappers: $method"
}
function Java([string]$method,[string[]]$cases){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('-Xmx128m','-cp',$classes,'dev.boom.prefix.PrefixReference',$method)){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $java=[Diagnostics.Process]::new();$java.StartInfo=$info
    try{if(-not $java.Start()){throw 'Prefix JVM reference failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.StandardInput.WriteAsync(($cases -join "`n")+"`n").Wait(30000)){throw 'Prefix JVM input stalled'};$java.StandardInput.Close();if(-not $java.WaitForExit(120000)){throw 'Prefix JVM reference timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};return @($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})}finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
}
function Bits([int]$n){([BitConverter]::ToUInt32([BitConverter]::GetBytes($n),0)).ToString('x')}
$pairs=[Collections.Generic.List[string]]::new();$triples=[Collections.Generic.List[string]]::new();$offsets=@([int]::MinValue,-1,0,1,2,7,8,9,15,16,17,31,32,33,[int]::MaxValue)
foreach($a in 0..15){foreach($b in 0..15){$pair=$a.ToString('x')+' '+$b.ToString('x');$pairs.Add($pair);foreach($off in $offsets){$triples.Add($pair+' '+(Bits $off))}}}
$raw=[Collections.Generic.List[string]]::new();for($i=0;$i -lt 65536;$i++){$raw.Add($i.ToString('x')+' '+(($i*109+37)-band65535).ToString('x')+' '+(Bits ($i%9-2)))}
$units=@(0,1,65,97,255,256,0xd7ff,0xd800,0xdbff,0xdc00,0xdfff,0xe000,65535);foreach($a in $units){foreach($b in $units){$raw.Add($a.ToString('x')+' '+$b.ToString('x')+' 1')}}
$random=[Random]::new(47047);$bytes=[byte[]]::new(4);for($i=0;$i -lt 256;$i++){$random.NextBytes($bytes);$a=[BitConverter]::ToUInt16($bytes,0);$b=[BitConverter]::ToUInt16($bytes,2);$raw.Add($a.ToString('x')+' '+$b.ToString('x')+' '+(Bits $offsets[$i%$offsets.Count]))}
$single=[Collections.Generic.List[string]]::new();foreach($n in 0..31){$single.Add($n.ToString('x'))};foreach($v in @('ffffffff','80000000','7fffffff','12345678')){$single.Add($v)};for($i=0;$i -lt 236;$i++){$random.NextBytes($bytes);$single.Add([BitConverter]::ToUInt32($bytes,0).ToString('x'))}
$count=0
foreach($method in @('offset','start','end','raw','dynamic','nullOrder','fullHeap','parallel')){
    [string[]]$cases=switch($method){offset {$triples.ToArray()};start {$pairs.ToArray()};end {$pairs.ToArray()};raw {$raw.ToArray()};default {$single.ToArray()}}
    $expected=Java $method $cases;$actual=[BoomNumericProbe]::Run($programs[$method].compilation.dll,(Join-Path $root fpstate.dll),$cases,'I',$true)
    if($actual.Count -ne $cases.Count -or ($actual -join '|') -cne ($expected -join '|')){throw "Prefix JVM/native mismatch: $method"}
    $count+=$cases.Count;Write-Output "Validated UTF16 prefix/suffix values, null ordering and FP state: $method"
}
if($raw.Count -ne 65961 -or $count -ne 71401){throw 'Prefix differential scope changed'}
[BoomPrefixProbe]::Native($programs.objects.compilation.dll,(Join-Path $root boom-runtime.dll))
[BoomPrefixProbe]::Boundary($programs.objects.compilation.dll,(Join-Path $root boom-runtime.dll),$false)
[BoomPrefixProbe]::Boundary($programs.objects.compilation.dll,(Join-Path $root boom-runtime.dll),$true)
[string[]]$workerCases=@(0..2048|ForEach-Object{$_.ToString('x')})
[int[]]$full=@((Java fullHeap $workerCases)|ForEach-Object{[BitConverter]::ToInt32([BitConverter]::GetBytes([Convert]::ToUInt32($_.Substring(2),16)),0)})
[BoomPrefixProbe]::FullHeap($programs.fullHeap.compilation.dll,(Join-Path $root boom-runtime.dll),$full)
[int[]]$workers=@((Java parallel $workerCases)|ForEach-Object{[BitConverter]::ToInt32([BitConverter]::GetBytes([Convert]::ToUInt32($_.Substring(2),16)),0)})
[BoomReplaceProbe]::Parallel($programs.parallel.compilation.dll,(Join-Path $root boom-runtime.dll),$workers)
$bridgeOut=Join-Path $root bridges;$bridgeArgs=@('inspect-jdk-bridges','--lock',$MetadataLock,'--jdk-base',$JdkBase,'--output',$bridgeOut);foreach($id in 1..12){$bridgeArgs+=@('--bridge-id',$id)}
& $Boom @bridgeArgs > (Join-Path $root bridges-inspect.json);if($LASTEXITCODE -ne 0){throw 'Prefix original bridge inspection failed'}
& D:/Dev/Python312/python.exe scripts/verify-jdk-bridges.py (Join-Path $bridgeOut inspection.json) > (Join-Path $root bridges-raw-check.json);if($LASTEXITCODE -ne 0){throw 'Prefix original raw Code/attribute verification failed'}
$bridges=Get-Content (Join-Path $root bridges-raw-check.json) -Raw|ConvertFrom-Json;if($bridges.bridges -ne 12 -or -not $bridges.passed){throw 'Prefix bridge scope changed'}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Prefix compiler changed during verification'}
$sources=[ordered]@{};foreach($path in @('native/runtime/string_prefix.asm','src/compiler/string_prefix.rs','src/compiler/jdk_bridges.rs','scripts/verify-jdk-bridges.py','tests/host/PrefixProbe.cs','tests/host/NumericProbe.cs','tests/host/ReplaceProbe.cs','java/subset/dev/boom/prefix/PrefixProgram.java','java/subset/dev/boom/prefix/PrefixReference.java','scripts/Test-StringPrefix.ps1')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_entries=9;JVM_differential_cases=$count;native_differential_calls=$count*2;raw_UTF16_JVM_cases=65961;all_UTF16_code_units=$true;original_startsWith_and_endsWith_wrappers_executed=$true;negative_offset_short_circuits_null_prefix=$true;nonnegative_offset_checks_null_before_bounds=$true;SSE2_vector_bytes=16;scalar_tail_and_empty_at_heap_end=$true;vector_backing_ends_at_arena_page_boundary=$true;no_access_guard_page_after_backing=$true;logical_tail_padding_not_compared=$true;native_no_allocation_relations=3375;full_heap_native_calls=8193;full_heap_source_calls=8193;pending_context_metadata_foreign_heap_and_corrupt_backing_checked=$true;GC_static_root_graph_checked=$true;workers=8;multicore_records=6147;bridges_raw_Code_and_all_attributes_checked=12;automatic_gc=$false;System_boot_phases_completed=$false;full_game_ready=$false;passed=$true;sources=$sources;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-string-prefix-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
