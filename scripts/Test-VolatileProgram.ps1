param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\client.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content -LiteralPath (Join-Path $projectRoot '.boom\latest-jdk-base.txt') -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path $projectRoot ('.boom\volatile-program-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content -LiteralPath $MetadataLock -Raw|ConvertFrom-Json
$sourceFiles=@(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'java\subset\dev\boom\volatilefields') -Filter '*.java' -File|ForEach-Object FullName)
& (Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes @sourceFiles (Join-Path $projectRoot 'java\subset\dev\boom\subset\ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Volatile reference javac failed'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
& (Join-Path $PSScriptRoot 'Build-VolatileProbe.ps1') -Output $root
$argsList=@('compile-program','--entry-class','dev/boom/volatilefields/VolatileEntry','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
foreach($file in Get-ChildItem -LiteralPath (Join-Path $classes 'dev\boom\volatilefields') -Filter '*.class'){$argsList+=@('--class-file',$file.FullName)}
$methods=@('byteValue','booleanValue','shortValue','charValue','intValue','longValue','floatValue','doubleValue','staticLong','staticDouble','reference','staticReference','neighbors','nullRead','stringValue','arrayValue')
$programs=@{}
foreach($method in ($methods+@('actor'))){
    $text=& $Boom @argsList --method $method --output (Join-Path $root $method)
    if($LASTEXITCODE -ne 0){throw "Volatile compilation failed: $method"}
    $p=$text|ConvertFrom-Json;$programs[$method]=$p
    if($p.schema -ne 12 -or -not $p.volatile_accesses -or $p.compilation.abi -ne 'context16-argv64-rax64-v1'){throw 'Volatile ordering contract missing'}
    $asm=Get-Content -LiteralPath $p.compilation.assembly -Raw
    if($asm -notmatch 'volatile acquire load' -or ($method -ne 'nullRead' -and $asm -notmatch 'xchg .*volatile SC store')){throw 'Expected ordered field operations are absent'}
    foreach($layout in $p.object_layouts){foreach($field in $layout.layout.fields){if($field.offset % $field.storage_bytes -ne 0){throw 'An actual field is not naturally aligned'}}}
    Write-Output "Compiled volatile entry: $method"
}
$flatPath=Join-Path $root 'flat'
$text=& $Boom compile-program --class-file (Join-Path $classes 'dev\boom\volatilefields\FlatVolatile.class') --entry-class dev/boom/volatilefields/FlatVolatile --method roundtrip --output $flatPath --assemble
if($LASTEXITCODE -ne 0){throw 'Legacy slot-layout volatile compilation failed'}
$programs['flat']=$text|ConvertFrom-Json
if($programs['flat'].schema -ne 12 -or $programs['flat'].object_layouts[0].layout.abi -ne 1){throw 'Legacy object ABI changed unexpectedly'}
$cases=[Collections.Generic.List[object]]::new()
$ints=@('0','1','2','7f','80','ff','100','7fff','8000','ffff','10000','ffffffff','80000000','7fffffff','12345678','abcdef01')
foreach($value in $ints){foreach($method in @('byteValue','booleanValue','shortValue','charValue','intValue','reference','staticReference','nullRead','stringValue','arrayValue','flat')){$cases.Add([pscustomobject]@{method=$method;values=@($value)})};foreach($other in $ints){$cases.Add([pscustomobject]@{method='neighbors';values=@($value,$other)})}}
$longs=@('0','1','ffffffff','ffffffffffffffff','8000000000000000','7fffffffffffffff','123456789abcdef0','abcdef0123456789')
foreach($value in $longs){foreach($method in @('longValue','staticLong')){$cases.Add([pscustomobject]@{method=$method;values=@($value)})}}
$floats=@('0','80000000','3f800000','7f800000','ff800000','7fc00001','7f800001','1','7fffff','800000','7f7fffff')
foreach($value in $floats){$cases.Add([pscustomobject]@{method='floatValue';values=@($value)})}
$doubles=@('0','8000000000000000','3ff0000000000000','7ff0000000000000','fff0000000000000','7ff8000000000001','7ff0000000000001','1','fffffffffffff','0010000000000000','7fefffffffffffff')
foreach($value in $doubles){foreach($method in @('doubleValue','staticDouble')){$cases.Add([pscustomobject]@{method=$method;values=@($value)})}}
$lines=@($cases|ForEach-Object{$class=if($_.method -eq 'flat'){'dev.boom.volatilefields.FlatVolatile'}else{'dev.boom.volatilefields.VolatileEntry'};$method=if($_.method -eq 'flat'){'roundtrip'}else{$_.method};(@($class,$method,$programs[$_.method].compilation.descriptor)+@($_.values)) -join ' '})
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Volatile JVM reference failed'}
    $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Volatile reference input stalled'}
    $oracle.StandardInput.Close();if(-not $oracle.WaitForExit(30000)){throw 'Volatile JVM reference timed out'}
    if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Volatile reference record count mismatch'}
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
$failures=[Collections.Generic.List[object]]::new()
foreach($method in ($methods+@('flat'))){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '});$m=$programs[$method].compilation
    if((Get-FileHash -LiteralPath $m.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $m.dll_digest.sha256){throw 'Volatile DLL changed'}
    $actual=[BoomNumericProbe]::Run($m.dll,(Join-Path $root 'fpstate.dll'),$values,[char]$m.descriptor[-1],$true)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add([pscustomobject]@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
Add-Type -Path (Join-Path $projectRoot 'tests\host\VolatileProbe.cs')
$stress=[Collections.Generic.List[object]]::new()
foreach($mode in @(0,3,6,9,12,15)){
    $count=if($mode -eq 0 -or $mode -eq 3){100000}else{10000}
    $forbidden=[BoomVolatileProbe]::Run($programs['actor'].compilation.dll,(Join-Path $root 'volatile-probe.dll'),$count,$mode,$true)
    $stress.Add([pscustomobject]@{mode=$mode;rounds=$count;forbidden=$forbidden})
}
$weak=Join-Path $root 'negative-control'
& (Join-Path $PSScriptRoot 'Build-VolatileWeakControl.ps1') -Program (Join-Path $root 'actor') -Output $weak
$negativeCount=200000
$negative=[BoomVolatileProbe]::Run((Join-Path $weak 'weak.dll'),(Join-Path $root 'volatile-probe.dll'),$negativeCount,0,$false)
if($negative -eq 0){throw 'Missing-order negative control was not sensitive on this machine'}
$report=[ordered]@{backend='boom-volatile-program-v12-masm-x64';runtime_language='assembly';compiled_entries=18;differential_cases=$cases.Count;native_executions=$cases.Count*2;primitive_widths_1_2_4_8=$true;float_double_raw_values=$true;inherited_volatile_fields=$true;legacy_slot_abi=$true;volatile_reference_string_and_array_fields=$true;volatile_loads='aligned x86-64 MOV, acquire';volatile_stores='memory XCHG, SC ordering';native_actor_harness=$true;managed_calls_between_actor_operations=$false;stress=@($stress.ToArray());positive_rounds=240000;positive_actor_invocations=480000;published_ordinary_state=$true;published_reference_graph_gc=$true;long_tearing_checked=$true;adjacent_narrow_fields=$true;negative_control=[ordered]@{test_only=$true;rounds=$negativeCount;forbidden_outcomes=$negative;detected_missing_ordering=$true};failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_memory_model_complete=$false;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 9
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText((Join-Path $projectRoot '.boom\latest-volatile-program.txt'),$root,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1}
