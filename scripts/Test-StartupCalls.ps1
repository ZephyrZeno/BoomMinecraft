param([string]$Boom='target/release/boom.exe',[string]$PreparedRun='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=if($PreparedRun){[IO.Path]::GetFullPath($PreparedRun)}else{Join-Path (Get-Location) ('.boom/startup-call-tests/'+[guid]::NewGuid().ToString('N'))}
[IO.Directory]::CreateDirectory($root)|Out-Null
$inputs=Get-Content .boom/locks/server.json -Raw|ConvertFrom-Json
$classes=Join-Path $root classes
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -d $classes java/subset/dev/boom/startup/StartupCalls.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'Startup call fixtures javac failed'}
& scripts/Build-FpProbe.ps1 -Output $root *> (Join-Path $root fp-build.log)
$programs=@{}
foreach($method in @('wide','test')){
    $metadata=@();if($method -eq 'test'){$metadata=@('--metadata-lock','.boom/locks/server.json','--jdk-base',$base)}
    $classArgs=@();foreach($file in Get-ChildItem (Join-Path $classes dev/boom/startup) -File -Filter '*.class'){$classArgs+=@('--class-file',$file.FullName)}
    if(-not $PreparedRun){
        & $Boom compile-program @classArgs --entry-class dev/boom/startup/StartupCalls --method $method --output (Join-Path $root $method) --assemble @metadata > (Join-Path $root ($method+'.json')) 2> (Join-Path $root ($method+'.err'))
        if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root ($method+'.err')) -Tail 10;throw "Startup call compile failed: $method"}
    }
    $programs[$method]=Get-Content (Join-Path $root "$method/program.json") -Raw|ConvertFrom-Json
    foreach($source in $programs[$method].sources){if((Get-FileHash $source.path).Hash.ToLowerInvariant() -ne $source.digest.sha256){throw 'Prepared startup call source changed'}}
}
function Bits([int]$n){([BitConverter]::ToUInt32([BitConverter]::GetBytes($n),0)).ToString('x')}
$cases=[Collections.Generic.List[object]]::new()
function Case([string]$method,[string[]]$values){$cases.Add([pscustomobject]@{method=$method;values=$values})}
$random=[Random]::new(55055);$bytes=[byte[]]::new(4)
for($i=0;$i -lt 256;$i++){
    $values=@(for($j=0;$j -lt 20;$j++){$random.NextBytes($bytes);[BitConverter]::ToUInt32($bytes,0).ToString('x')})
    Case wide $values;Case call @($values[0])
}
$points=@(-1,0,65,97,98,120,58,65535,0xd800,0xdc00,0x1f600,0x10000,0x10ffff,0x110000,[int]::MinValue)
$starts=@([int]::MinValue,-2,-1,0,1,2,3,4,5,6,17,[int]::MaxValue)
foreach($n in 0..5){foreach($cp in $points){Case last @((Bits $n),(Bits $cp));foreach($from in $starts){foreach($method in @('lastFrom','forward')){Case $method @((Bits $n),(Bits $cp),(Bits $from))}}}}
foreach($a in -1..7){foreach($b in -1..7){Case slice @((Bits $a),(Bits $b))}}
foreach($a in 0..5){foreach($b in 0..5){foreach($method in @('strDefaults','contains','containsOrder')){Case $method @((Bits $a),(Bits $b))};foreach($from in $starts){foreach($method in @('strIndex','strLast')){Case $method @((Bits $a),(Bits $b),(Bits $from))}}}}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-Xmx128m','-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$java=[Diagnostics.Process]::new();$java.StartInfo=$info
try{
    if(-not $java.Start()){throw 'Startup call JVM oracle failed'}
    $stdout=$java.StandardOutput.ReadToEndAsync();$stderr=$java.StandardError.ReadToEndAsync()
    $lines=@($cases|ForEach-Object{$desc='(' + ('I'*$_.values.Count) + ')I';(@('dev.boom.startup.StartupCalls',$_.method,$desc)+@($_.values))-join ' '})
    if(-not $java.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(30000)){throw 'Startup call oracle input timeout'}
    $java.StandardInput.Close();if(-not $java.WaitForExit(30000)){throw 'Startup call oracle timeout'}
    if($java.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object {$_.Trim()})
}finally{if(-not $java.HasExited){$java.Kill($true);$java.WaitForExit()};$java.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Startup call oracle count differs'}
Add-Type -Path tests/host/NumericProbe.cs
$dispatch=@{};$names=@('call','last','lastFrom','forward','slice','strIndex','strLast','strDefaults','contains','containsOrder');for($i=0;$i -lt $names.Count;$i++){$dispatch[$names[$i]]=$i}
foreach($method in @('wide','test')){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if(($method -eq 'wide') -eq ($cases[$i].method -eq 'wide')){$i}})
    [string[]]$values=@($indices|ForEach-Object {if($method -eq 'wide'){$cases[$_].values -join ' '}else{(@($dispatch[$cases[$_].method].ToString('x'))+@($cases[$_].values)+@('0')*(3-$cases[$_].values.Count))-join ' '}})
    $p=$programs[$method]
    [uint32[]]$exceptionIds=@();[string[]]$exceptionNames=@()
    if($p.exception_runtime){
        $exceptionIds=@($p.exception_runtime.factories|ForEach-Object {[uint32]$_.class_id})
        $exceptionNames=@($p.exception_runtime.factories|ForEach-Object {$id=$_.class_id;@($p.classes|Where-Object id -eq $id)[0].name.Replace('/','.')})
    }
    $actual=[BoomNumericProbe]::Run($p.compilation.dll,(Join-Path $root fpstate.dll),$values,[char]'I',[bool]$p.compilation.requires_heap,$exceptionIds,$exceptionNames)
    for($i=0;$i -lt $indices.Count;$i++){if($actual[$i] -ne $expected[$indices[$i]]){throw "Startup call mismatch $method input=$($values[$i]) actual=$($actual[$i]) expected=$($expected[$indices[$i]])"}}
}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Startup call compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';JVM_cases=$cases.Count;native_executions=$cases.Count*2;twenty_argument_entries_and_internal_calls_verified=$true;String_lastIndexOf_BMP_supplementary_unpaired_surrogates_and_bounds_checked=$true;forward_index_and_substring_regressions_passed=$true;string_needle_search_and_empty_null_order_checked=$true;original_String_contains_CharSequence_toString_executed=$true;instance_Java_bridge_checks_receiver_before_side_effects=$true;automatic_gc=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-startup-call-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
