param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/string-chars-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-string-chars-test.txt',$root,[Text.UTF8Encoding]::new($false))
$classes=Join-Path $root classes;$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/chars/CharsProgram.java java/subset/dev/boom/chars/CharsReference.java
if($LASTEXITCODE -ne 0){throw 'Character copy reference javac failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root *> (Join-Path $root runtime-build.log)
& scripts/Build-FpProbe.ps1 -Output $root *> (Join-Path $root fp-build.log)
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/ReplaceProbe.cs
Add-Type -Path tests/host/CharsProbe.cs
$methods=@('objects','array','pair','relation','twice','dynamic','bounds','nullReceiver','fullHeap','copyTypes','parallel');$programs=@{}
foreach($method in $methods){
    $descriptor=switch($method){objects {'(I)Ljava/lang/String;'};array {'(I)[C'};pair {'(II)[C'};relation {'(II)I'};default {'(I)I'}}
    $out=Join-Path $root $method
    & $Boom compile-program --class-file (Join-Path $classes dev/boom/chars/CharsProgram.class) --entry-class dev/boom/chars/CharsProgram --method $method --descriptor $descriptor --metadata-lock $MetadataLock --jdk-base $JdkBase --output $out --assemble > (Join-Path $root ($method+'-compile.json')) 2> (Join-Path $root ($method+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'-compile.err')) -Tail 14;throw "String character copy compilation failed: $method"}
    $p=Get-Content (Join-Path $out program.json) -Raw|ConvertFrom-Json
    if($p.schema -ne 45 -or $p.string_chars.Count -eq 0 -or $p.full_game_ready){throw 'String character copy source binding missing'}
    foreach($b in $p.string_chars){
        if($b.abi -ne 1 -or $b.storage_abi -ne 3 -or $b.compact_strings -or $b.origin.sha256 -ne $base.classes.'java.lang.String'.sha256 -or $b.utf16_origin.sha256 -ne $base.classes.'java.lang.StringUTF16'.sha256 -or $b.latin1_origin.sha256 -ne $base.classes.'java.lang.StringLatin1'.sha256){throw 'Character copy original source/storage proof changed'}
        foreach($entry in @(@('native_source_sha256','native/runtime/string_chars.asm'),@('string_source_sha256','native/runtime/strings.asm'),@('heap_source_sha256','native/runtime/heap.asm'))){if($b.($entry[0]) -ne (Get-FileHash $entry[1]).Hash.ToLowerInvariant()){throw 'Character copy runtime proof changed'}}
    }
    $programs[$method]=$p;Write-Output "Compiled source-verified String.toCharArray: $method"
}
function Java([string]$method,[string[]]$cases){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('-Xmx128m','-cp',$classes,'dev.boom.chars.CharsReference',$method)){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $java=[Diagnostics.Process]::new();$java.StartInfo=$info
    try{if(-not $java.Start()){throw 'Character copy JVM reference failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.StandardInput.WriteAsync(($cases -join "`n")+"`n").Wait(30000)){throw 'Character copy JVM input stalled'};$java.StandardInput.Close();if(-not $java.WaitForExit(120000)){throw 'Character copy JVM reference timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};return @($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})}finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
}
$units=@(0,1,65,97,255,256,0xd7ff,0xd800,0xdbff,0xdc00,0xdfff,0xe000,65535)
$raw=[Collections.Generic.List[string]]::new();for($i=0;$i -lt 65536;$i++){$raw.Add($i.ToString('x')+' '+(($i*109+37)-band65535).ToString('x'))}
foreach($a in $units){foreach($b in $units){$raw.Add($a.ToString('x')+' '+$b.ToString('x'))}}
$random=[Random]::new(45045);$bytes=[byte[]]::new(4)
for($i=0;$i -lt 256;$i++){$random.NextBytes($bytes);$a=[BitConverter]::ToUInt16($bytes,0);$b=[BitConverter]::ToUInt16($bytes,2);$raw.Add($a.ToString('x')+' '+$b.ToString('x'))}
if($raw.Count -ne 65961){throw 'Raw character copy scope changed'}
$expected=Java pair $raw.ToArray();$actual=[BoomCharsProbe]::Raw($programs.pair.compilation.dll,$raw.ToArray())
if($actual.Count -ne $raw.Count -or $expected.Count -ne $raw.Count -or ($actual -join '|') -cne ($expected -join '|')){throw 'Raw UTF16 character copy/JVM output mismatch'}
Write-Output 'Validated every UTF16 code unit, NUL, surrogate pairs and unpaired surrogates'
$pairs=[Collections.Generic.List[string]]::new();foreach($n in 0..15){foreach($v in $units){$pairs.Add($n.ToString('x')+' '+$v.ToString('x'))}}
for($i=0;$i -lt 128;$i++){$random.NextBytes($bytes);$n=[BitConverter]::ToUInt32($bytes,0);$random.NextBytes($bytes);$v=[BitConverter]::ToUInt32($bytes,0);$pairs.Add($n.ToString('x')+' '+$v.ToString('x'))}
$single=[Collections.Generic.List[string]]::new();foreach($n in 0..31){$single.Add($n.ToString('x'))};foreach($v in @('ffffffff','80000000','7fffffff','12345678')){$single.Add($v)};for($i=0;$i -lt 236;$i++){$random.NextBytes($bytes);$single.Add([BitConverter]::ToUInt32($bytes,0).ToString('x'))}
$count=0
foreach($method in @('relation','twice','dynamic','bounds','nullReceiver','fullHeap','copyTypes','parallel')){
    [string[]]$cases=if($method -eq 'relation'){$pairs.ToArray()}else{$single.ToArray()}
    $expected=Java $method $cases;$actual=[BoomNumericProbe]::Run($programs[$method].compilation.dll,(Join-Path $root fpstate.dll),$cases,'I',$true)
    if($actual.Count -ne $cases.Count -or ($actual -join '|') -cne ($expected -join '|')){throw "Character copy numeric/identity JVM mismatch: $method"}
    $count+=$cases.Count;Write-Output "Validated source character copies, identity, exception and FP state: $method"
}
if($count -ne 2240){throw 'Character copy numeric scope changed'}
[BoomCharsProbe]::Objects($programs.objects.compilation.dll,(Join-Path $root boom-runtime.dll))
[BoomCharsProbe]::Tail($programs.objects.compilation.dll,(Join-Path $root boom-runtime.dll))
[BoomCharsProbe]::FullHeap($programs.fullHeap.compilation.dll,(Join-Path $root boom-runtime.dll))
[string[]]$parallelCases=@(0..2048|ForEach-Object{$_.ToString('x')})
[int[]]$parallel=@((Java parallel $parallelCases)|ForEach-Object{[BitConverter]::ToInt32([BitConverter]::GetBytes([Convert]::ToUInt32($_.Substring(2),16)),0)})
[BoomReplaceProbe]::Parallel($programs.parallel.compilation.dll,(Join-Path $root boom-runtime.dll),$parallel)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Character copy compiler changed during verification'}
$sources=[ordered]@{};foreach($path in @('native/runtime/string_chars.asm','src/compiler/string_chars.rs','tests/host/CharsProbe.cs','tests/host/ReplaceProbe.cs','java/subset/dev/boom/chars/CharsProgram.java','java/subset/dev/boom/chars/CharsReference.java','scripts/Test-StringChars.ps1')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_entries=11;raw_UTF16_JVM_cases=$raw.Count;numeric_JVM_cases=$count;numeric_native_executions=$count*2;all_UTF16_units_including_NUL_and_surrogates=$true;fresh_array_including_empty=$true;source_and_independent_copy_mutation_isolated=$true;one_allocation_per_copy_calls=512;full_heap_source_OOM_catch_calls=256;empty_array_at_exact_heap_end=$true;GC_root_graph_verified=$true;OOM_recovery=$true;metadata_foreign_heap_and_pending_exception_gates=$true;workers=8;multicore_records=6147;automatic_gc=$false;descriptorString_complete=$false;full_game_ready=$false;passed=$true;sources=$sources;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-string-chars-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
