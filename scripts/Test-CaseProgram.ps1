param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path (Get-Location) ('.boom/case-program-tests/'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
[IO.File]::WriteAllText('.boom/current-case-program.txt',$root,[Text.UTF8Encoding]::new($false))
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json;$base=Get-Content $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) 'javac.exe') --release 21 -g -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/casing/CaseProgram.java java/subset/dev/boom/casing/MappingOracle.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'Case fixture javac failed'}
$mapping=Join-Path $root 'jdk-mappings.bin'
& $inputs.java.executable -cp $classes dev.boom.casing.MappingOracle $mapping > (Join-Path $root 'mapping-reference.txt')
if($LASTEXITCODE -ne 0){throw 'Case mapping oracle failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root > (Join-Path $root 'runtime-build.log') 2>&1
& scripts/Build-FpProbe.ps1 -Output $root > (Join-Path $root 'fp-build.log') 2>&1
Add-Type -Path tests/host/CaseProbe.cs
Add-Type -Path tests/host/NumericProbe.cs
[BoomCaseProbe]::AllMappings((Join-Path $root 'boom-runtime.dll'),$mapping)
Write-Output 'Validated 2228224 ASM simple mappings against Java 21'
$programs=@{};$methods=@('compare','literals','longValues','unequal','nullArgument','nullReceiver','parallel','identity','indexOf','indexFrom','suffix','range','emptyIdentity','fullIdentity','substringOom')
foreach($method in $methods){
    $descriptor=if($method -in @('compare','indexFrom','range')){'(II)I'}else{'(I)I'}
    & $Boom compile-program --class-file (Join-Path $classes 'dev/boom/casing/CaseProgram.class') --entry-class dev/boom/casing/CaseProgram --method $method --descriptor $descriptor --metadata-lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root $method) --assemble > (Join-Path $root ($method+'-compile.json')) 2> (Join-Path $root ($method+'-compile.err'))
    if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'-compile.err')) -Tail 20;throw "Case compilation failed: $method"}
    $p=Get-Content (Join-Path $root ($method+'/program.json')) -Raw|ConvertFrom-Json
    if($p.schema -ne 31 -or $p.string_case.abi -ne 1 -or $p.string_case.data.mapping_rows -ne 2879 -or $p.string_case.data.unicode_version -ne '15.0.0' -or $p.string_case.character_origins.Count -ne 10 -or $p.string_case.string_origin.sha256 -ne $base.classes.'java.lang.String'.sha256 -or $p.string_case.bindings.Count -eq 0){throw 'Case data/source profile missing'}
    foreach($o in $p.string_case.character_origins){if($o.sha256 -ne $base.classes.($o.binary_name).sha256){throw 'Character data source proof changed'}}
    if(($method -in @('nullReceiver','substringOom')) -ne ($null -ne $p.exception_runtime)){throw 'Case comparison changed the Context32 boundary'}
    $programs[$method]=$p;Write-Output "Compiled Unicode String method: $method"
}
function Java([string]$text){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($a in @('-Xmx128m','-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($a)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $java=[Diagnostics.Process]::new();$java.StartInfo=$info
    try{if(-not $java.Start()){throw 'Case JVM reference failed'};$stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync();if(-not $java.StandardInput.WriteAsync($text).Wait(15000)){throw 'Case JVM input stalled'};$java.StandardInput.Close();if(-not $java.WaitForExit(30000)){throw 'Case JVM reference timed out'};if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()};return $stdout.GetAwaiter().GetResult()}
    finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
}
$cases=@{};$cases.compare=[Collections.Generic.List[string]]::new()
$bytes=[IO.File]::ReadAllBytes($mapping)
function BE32([int]$offset){([uint32]$bytes[$offset]*16777216L)+([uint32]$bytes[$offset+1]*65536L)+([uint32]$bytes[$offset+2]*256L)+[uint32]$bytes[$offset+3]}
for($i=8;$i -lt $bytes.Length;$i+=12){$cp=BE32 $i;$upper=BE32 ($i+4);$lower=BE32 ($i+8);$cases.compare.Add($cp.ToString('x')+' '+$upper.ToString('x'));$cases.compare.Add($cp.ToString('x')+' '+$lower.ToString('x'))}
foreach($a in @(0,65,97,0x130,0x131,0xd800,0xd801,0xdbff,0xdc00,0xdfff,0x10000,0x10400,0x10428,0x10ffff)){foreach($b in @(0,65,97,0x130,0x131,0xd800,0xd801,0xdbff,0xdc00,0xdfff,0x10000,0x10400,0x10428,0x10ffff)){$cases.compare.Add($a.ToString('x')+' '+$b.ToString('x'))}}
[uint64]$seed=0x12345678
for($i=0;$i -lt 512;$i++){$seed=($seed*1664525+1013904223) -band 0xffffffffL;$a=$seed%0x110000;$seed=($seed*1664525+1013904223) -band 0xffffffffL;$b=$seed%0x110000;$cases.compare.Add($a.ToString('x')+' '+$b.ToString('x'))}
$values=[Collections.Generic.List[string]]::new();foreach($n in @(0,1,2,3,4,5,7,8,9,15,16,17,127,128,255,32767,65535,2147483648,[uint32]::MaxValue,2147483647)){$values.Add(([uint32]$n).ToString('x'))}
for($i=0;$i -lt 96;$i++){$seed=($seed*1664525+1013904223) -band 0xffffffffL;$values.Add($seed.ToString('x'))}
foreach($method in $methods|Where-Object {$_ -ne 'compare'}){$cases[$method]=$values}
$cases.indexFrom=[Collections.Generic.List[string]]::new();$cases.range=[Collections.Generic.List[string]]::new();$cases.suffix=[Collections.Generic.List[string]]::new();$cases.indexOf=[Collections.Generic.List[string]]::new()
foreach($cp in @(-1,0,65,97,0x3a3,0xd800,0xd801,0xdc00,0x10400,0x10428,0x10ffff,0x110000,[int]::MinValue,[int]::MaxValue)){$bits=([BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$cp),0)).ToString('x');$cases.indexOf.Add($bits);foreach($start in @(-2,-1,0,1,2,3,4,5,6,7,8,9,10,11,[int]::MinValue,[int]::MaxValue)){$other=([BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$start),0)).ToString('x');$cases.indexFrom.Add($bits+' '+$other)}}
foreach($begin in @(-2,-1,0,1,2,3,4,5,6,7,8,9,10,11,[int]::MinValue,[int]::MaxValue)){$bits=([BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$begin),0)).ToString('x');$cases.suffix.Add($bits);foreach($end in @(-2,-1,0,1,2,3,4,5,6,7,8,9,10,11,[int]::MinValue,[int]::MaxValue)){$other=([BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$end),0)).ToString('x');$cases.range.Add($bits+' '+$other)}}
$lines=@(foreach($method in $methods){foreach($value in $cases[$method]){'dev.boom.casing.CaseProgram '+$method+' '+$(if($method -in @('compare','indexFrom','range')){'(II)I'}else{'(I)I'})+' '+$value}})
$expected=@((Java (($lines -join "`n")+"`n")).Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {$_.Trim()})
if($expected.Count -ne $lines.Count){throw 'Case JVM reference count mismatch'}
$index=0
foreach($method in $methods){$actual=[BoomNumericProbe]::Run($programs[$method].compilation.dll,(Join-Path $root 'fpstate.dll'),$cases[$method].ToArray(),'I',$true);foreach($value in $actual){if($value -ne $expected[$index]){throw "Case JVM mismatch: $method, $index, native=$value, JVM=$($expected[$index])"};$index++};Write-Output "Validated native String semantics, source case data and GC: $method"}
$parallelLines=@(foreach($i in 0..2048){'dev.boom.casing.CaseProgram parallel (I)I '+$i.ToString('x')})
$parallelExpected=@((Java (($parallelLines -join "`n")+"`n")).Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {[int][Convert]::ToUInt32($_.Trim().Substring(2),16)})
[BoomCaseProbe]::ParallelAndNoAllocation($programs.parallel.compilation.dll,(Join-Path $root 'boom-runtime.dll'),[int[]]$parallelExpected)
[BoomCaseProbe]::FullHeapSubstring($programs.substringOom.compilation.dll,(Join-Path $root 'boom-runtime.dll'))
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Case compiler changed during run'}
$report=[ordered]@{backend='boom-unicode-comparison-program-v31-masm-x64';compiler_sha256=$sha;runtime_language='assembly';compiled_entries=$methods.Count;differential_cases=$lines.Count;native_executions=($lines.Count*2);exhaustive_Unicode_code_points=1114112;native_mapping_comparisons=2228224;unicode_version='15.0.0';mapping_rows=2879;source_Character_data_hashes_verified=$true;UnicodeData_and_JDK_exhaustive_agreement=$true;BMP_supplementary_and_isolated_surrogates=$true;actual_String_equalsIgnoreCase=$true;null_receiver_uses_Context32_catch=$true;workers=8;multicore_records=6147;hot_no_allocation_calls=4099;temporary_graph_reclaimed=$true;String_toLowerCase_Locale_complete=$false;Locale_and_System_application_bootstrap_complete=$false;automatic_gc=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 7
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-case-program.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
