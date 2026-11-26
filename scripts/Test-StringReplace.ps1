param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/string-replace-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-string-replace-test.txt',$root,[Text.UTF8Encoding]::new($false))
$classes=Join-Path $root classes;$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/replace/ReplaceProgram.java java/subset/dev/boom/replace/ReplaceReference.java
if($LASTEXITCODE -ne 0){throw 'Replacement reference javac failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
& scripts/Build-FpProbe.ps1 -Output $root *> (Join-Path $root fp-build.log)
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/ReplaceProbe.cs
$methods=@('objects','pair','relation','twice','dynamic','allocation','fullHeap','nullReceiver','parallel');$programs=@{}
foreach($method in $methods){
    $descriptor=switch($method){objects {'(I)Ljava/lang/String;'};pair {'(II)Ljava/lang/String;'};relation {'(III)I'};twice {'(III)I'};default {'(I)I'}}
    $out=Join-Path $root $method
    & $Boom compile-program --class-file (Join-Path $classes dev/boom/replace/ReplaceProgram.class) --entry-class dev/boom/replace/ReplaceProgram --method $method --descriptor $descriptor --metadata-lock $MetadataLock --jdk-base $JdkBase --output $out --assemble > (Join-Path $root ($method+'-compile.json')) 2> (Join-Path $root ($method+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'-compile.err')) -Tail 14;throw "String replacement compilation failed: $method"}
    $p=Get-Content (Join-Path $out program.json) -Raw|ConvertFrom-Json
    if($p.schema -ne 40 -or $p.string_replace.Count -eq 0 -or $p.full_game_ready){throw 'String replacement source binding missing'}
    foreach($b in $p.string_replace){if($b.abi -ne 1 -or $b.storage_abi -ne 3 -or $b.compact_strings -or $b.origin.sha256 -ne $base.classes.'java.lang.String'.sha256 -or $b.utf16_origin.sha256 -ne $base.classes.'java.lang.StringUTF16'.sha256 -or $b.latin1_origin.sha256 -ne $base.classes.'java.lang.StringLatin1'.sha256){throw 'String replacement original source/storage proof changed'};foreach($entry in @(@('native_source_sha256','native/runtime/string_replace.asm'),@('string_source_sha256','native/runtime/strings.asm'),@('dynamic_source_sha256','native/runtime/string_dynamic.asm'),@('heap_source_sha256','native/runtime/heap.asm'))){if($b.($entry[0]) -ne (Get-FileHash $entry[1]).Hash.ToLowerInvariant()){throw 'Replacement runtime proof changed'}}}
    $programs[$method]=$p;Write-Output "Compiled source-verified String.replace(char,char): $method"
}
function Java([string]$method,[string[]]$cases){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('-Xmx128m','-cp',$classes,'dev.boom.replace.ReplaceReference',$method)){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $java=[Diagnostics.Process]::new();$java.StartInfo=$info
    try{if(-not $java.Start()){throw 'Replacement JVM reference failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.StandardInput.WriteAsync(($cases -join "`n")+"`n").Wait(30000)){throw 'Replacement JVM input stalled'};$java.StandardInput.Close();if(-not $java.WaitForExit(120000)){throw 'Replacement JVM reference timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};return @($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})}finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
}
$units=@(0,1,65,97,255,256,0xd7ff,0xd800,0xdbff,0xdc00,0xdfff,0xe000,65535)
$raw=[Collections.Generic.List[string]]::new();for($i=0;$i -lt 65536;$i++){$raw.Add($i.ToString('x')+' '+(($i*109+37)-band65535).ToString('x'))}
foreach($a in $units){foreach($b in $units){$raw.Add($a.ToString('x')+' '+$b.ToString('x'))}}
$random=[Random]::new(40040);$bytes=[byte[]]::new(4)
for($i=0;$i -lt 512;$i++){$random.NextBytes($bytes);$a=[BitConverter]::ToUInt16($bytes,0);$b=[BitConverter]::ToUInt16($bytes,2);$raw.Add($a.ToString('x')+' '+$b.ToString('x'))}
if($raw.Count -ne 66217){throw 'Raw UTF16 replacement scope changed'}
$expected=Java pair $raw.ToArray();$actual=[BoomReplaceProbe]::Raw($programs.pair.compilation.dll,$raw.ToArray())
if($actual.Count -ne $raw.Count -or $expected.Count -ne $raw.Count -or ($actual -join '|') -cne ($expected -join '|')){throw 'Raw UTF16 replacement/JVM output mismatch'}
Write-Output 'Validated all 65536 UTF16 units plus edge pairs and random raw replacement results'
$triple=[Collections.Generic.List[string]]::new();foreach($n in 0..7){foreach($a in $units){foreach($b in $units){$triple.Add($n.ToString('x')+' '+$a.ToString('x')+' '+$b.ToString('x'))}}}
for($i=0;$i -lt 128;$i++){$random.NextBytes($bytes);$n=[BitConverter]::ToUInt32($bytes,0);$random.NextBytes($bytes);$a=[BitConverter]::ToUInt32($bytes,0);$random.NextBytes($bytes);$b=[BitConverter]::ToUInt32($bytes,0);$triple.Add($n.ToString('x')+' '+$a.ToString('x')+' '+$b.ToString('x'))}
$single=[Collections.Generic.List[string]]::new();foreach($n in 0..31){$single.Add($n.ToString('x'))};foreach($v in @('ffffffff','80000000','7fffffff','12345678')){$single.Add($v)};for($i=0;$i -lt 236;$i++){$random.NextBytes($bytes);$single.Add([BitConverter]::ToUInt32($bytes,0).ToString('x'))}
$count=0
foreach($method in @('relation','twice','dynamic','allocation','fullHeap','nullReceiver','parallel')){
    [string[]]$cases=if($method -in @('relation','twice')){$triple.ToArray()}else{$single.ToArray()}
    $expected=Java $method $cases;$actual=[BoomNumericProbe]::Run($programs[$method].compilation.dll,(Join-Path $root fpstate.dll),$cases,'I',$true)
    if($actual.Count -ne $cases.Count -or ($actual -join '|') -cne ($expected -join '|')){throw "Replacement numeric/identity JVM mismatch: $method"}
    $count+=$cases.Count;Write-Output "Validated replacement values, identity, GC and FP environment: $method"
}
if($count -ne 4320){throw 'Replacement numeric scope changed'}
[BoomReplaceProbe]::Objects($programs.objects.compilation.dll,(Join-Path $root boom-runtime.dll))
[BoomReplaceProbe]::Tail($programs.objects.compilation.dll,(Join-Path $root boom-runtime.dll))
[BoomReplaceProbe]::FullHeap($programs.fullHeap.compilation.dll,(Join-Path $root boom-runtime.dll))
[string[]]$parallelCases=@(0..2048|ForEach-Object{$_.ToString('x')})
[int[]]$parallel=@((Java parallel $parallelCases)|ForEach-Object{[BitConverter]::ToInt32([BitConverter]::GetBytes([Convert]::ToUInt32($_.Substring(2),16)),0)})
[BoomReplaceProbe]::Parallel($programs.parallel.compilation.dll,(Join-Path $root boom-runtime.dll),$parallel)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Replacement compiler changed during verification'}
$sources=[ordered]@{};foreach($path in @('native/runtime/string_replace.asm','native/runtime/string_concat_api.asm','src/compiler/string_replace.rs','tests/host/ReplaceProbe.cs','java/subset/dev/boom/replace/ReplaceProgram.java','java/subset/dev/boom/replace/ReplaceReference.java','scripts/Test-StringReplace.ps1')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_entries=9;raw_UTF16_JVM_cases=66217;numeric_JVM_cases=$count;numeric_native_executions=$count*2;all_UTF16_units_including_NUL_and_surrogates=$true;identity_preserved_on_equal_or_missing_char=$true;changed_results_have_private_String_and_char_array=$true;zero_allocation_budget_calls=384;changed_two_allocation_budget_calls=128;full_heap_source_calls=256;full_heap_identity_calls=128;full_heap_OOM_catch_calls=128;partial_allocation_OOM_and_recovery=$true;valid_empty_backing_at_exact_heap_end_in_replace_and_concat=$true;metadata_heap_and_pending_exception_gates=$true;workers=8;multicore_records=6147;automatic_gc=$false;descriptorString_complete=$false;SystemProps_initProperties_complete=$false;full_game_ready=$false;passed=$true;sources=$sources;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-string-replace-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
