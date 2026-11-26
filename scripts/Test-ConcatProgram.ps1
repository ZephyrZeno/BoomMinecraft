param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\client.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content -LiteralPath (Join-Path $projectRoot '.boom\latest-jdk-base.txt') -Raw).Trim()) 'jdk-base.json'}
$tools=Get-Content -LiteralPath (Join-Path $projectRoot '.boom\toolchain.json') -Raw|ConvertFrom-Json
$boomPath=(Resolve-Path -LiteralPath $Boom).Path
$root=Join-Path $projectRoot ('.boom\concat-program-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$sources=@(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'java\subset\dev\boom\concat') -Filter '*.java' -File|ForEach-Object FullName)
& (Join-Path (Split-Path -Parent $tools.java) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes @sources (Join-Path $projectRoot 'java\subset\dev\boom\subset\ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Concat reference javac failed.'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
$baseArgs=@('compile-program','--entry-class','dev/boom/concat/ConcatEntry','--assemble')
foreach($file in Get-ChildItem -LiteralPath (Join-Path $classes 'dev\boom\concat') -Filter '*.class' -File){$baseArgs+=@('--class-file',$file.FullName)}
$methods=@('intHash','longHash','character','longCharacter','longLength','classNameConcat','mixed','controlConstants','nested','independent','interned','internBeforeLiteral','literalBeforeIntern','collisions','arrays','state')
$programs=@{};$manifests=@{}
foreach($method in $methods){
    $metadataArgs=if($method -eq 'classNameConcat'){@('--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase)}else{@()}
    $text=& $boomPath @baseArgs @metadataArgs --method $method --output (Join-Path $root $method)
    if($LASTEXITCODE -ne 0){throw "Concat compilation failed: $method"}
    $program=$text|ConvertFrom-Json;$programs[$method]=$program;$manifests[$method]=$program.compilation
    if($program.schema -ne 6 -or $program.bootstrap_string_abi -ne 3 -or -not $program.dynamic_string_runtime -or -not $program.compilation.requires_heap){throw 'Unexpected concat runtime contract.'}
}
$cases=[Collections.Generic.List[object]]::new()
function Bits([int]$value){return ([BitConverter]::ToUInt32([BitConverter]::GetBytes($value),0)).ToString('x')}
function AddCase([string]$method,[string[]]$values){$cases.Add([pscustomobject]@{method=$method;values=$values})}
$ints=@([int]::MinValue,[int]::MaxValue,-1000000000,-65536,-10,-1,0,1,7,9,10,127,128,65535,1000000000)
$longs=@('0','1','9','a','7fffffff','80000000','ffffffff','100000000','7fffffffffffffff','8000000000000000','ffffffffffffffff','fedcba9876543210')
foreach($value in $ints){
    foreach($method in @('intHash','controlConstants','independent','interned','internBeforeLiteral','literalBeforeIntern','collisions','state','classNameConcat')){AddCase $method @((Bits $value))}
    foreach($index in (@(-1,[int]::MinValue,[int]::MaxValue)+@(0..26))){AddCase 'character' @((Bits $value),(Bits $index))}
    foreach($wide in $longs){AddCase 'nested' @((Bits $value),$wide)}
}
foreach($wide in $longs){AddCase 'longHash' @($wide);AddCase 'longLength' @($wide);foreach($index in (@(-1,[int]::MinValue,[int]::MaxValue)+@(0..26))){AddCase 'longCharacter' @($wide,(Bits $index))}}
foreach($which in 0..7){foreach($unit in @(0,1,2,65,255,65535,55296,57343)){
    foreach($flag in @(-1,0,1)){AddCase 'mixed' @((Bits $ints[$which]),$longs[$which],(Bits $flag),(Bits $unit),(Bits $which))}
}}
foreach($count in @(-1,0,1,2,7,17)){foreach($index in @(-1,0,1,($count-1),$count)){
    foreach($value in @([int]::MinValue,-1,0,7,[int]::MaxValue)){AddCase 'arrays' @((Bits $count),(Bits $index),(Bits $value))}
}}
$lines=@($cases|ForEach-Object{(@('dev.boom.concat.ConcatEntry',$_.method,$manifests[$_.method].descriptor)+@($_.values)) -join ' '})
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$tools.java;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Concat JVM reference failed.'}
    $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Concat JVM input stalled.'}
    $oracle.StandardInput.Close();if(-not $oracle.WaitForExit(30000)){throw 'Concat JVM reference timed out.'}
    if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Concat reference count mismatch.'}
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '});$manifest=$manifests[$method]
    if((Get-FileHash -LiteralPath $manifest.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.dll_digest.sha256){throw 'Concat module hash mismatch.'}
    $actual=[BoomNumericProbe]::Run($manifest.dll,(Join-Path $root 'fpstate.dll'),$values,'I',$true)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add([pscustomobject]@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
$rejections=0
foreach($method in @('rejectedFloat','rejectedObject','rejectedLambda')){
    $destination=Join-Path $root ('reject-'+$method)
    & $boomPath @baseArgs --method $method --output $destination 2>&1|Out-Null
    if($LASTEXITCODE -eq 0 -or (Test-Path -LiteralPath $destination)){throw 'Unsupported dynamic conversion/bootstrap accepted.'};$rejections++
}
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
Add-Type -Path (Join-Path $projectRoot 'tests\host\DynamicStringProbe.cs')
[BoomDynamicStringProbe]::AbiAndFailure((Join-Path $root 'boom-runtime.dll'))
[BoomDynamicStringProbe]::Cold($manifests['interned'].dll,(Join-Path $root 'boom-runtime.dll'))
$report=[ordered]@{backend='boom-concat-program-v6-masm-x64';runtime_language='assembly';string_pool_abi=3;compiled_entries=$methods.Count;differential_cases=$cases.Count;native_executions=$cases.Count*2;cold_intern_records=4099;integer_and_long_min_values=$true;boolean_char_null_and_utf16=$true;bootstrap_recipe_static_controls=$true;dynamic_string_identity=$true;intern_before_and_after_literal=$true;hash_collision_values_distinct=$true;growable_intern_table=$true;quiescent_gc_roots=$true;native_oom_recovery_and_heap_binding=$true;unsupported_operations_rejected=$rejections;failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1}
