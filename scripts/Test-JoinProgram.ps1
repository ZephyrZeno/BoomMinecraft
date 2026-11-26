param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path (Get-Location) ('.boom/join-program-tests/'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/join/JoinEntry.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'String join javac reference failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root
& scripts/Build-FpProbe.ps1 -Output $root
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/JoinProbe.cs
$common=@('compile-program','--entry-class','dev/boom/join/JoinEntry','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
foreach($f in Get-ChildItem (Join-Path $classes 'dev/boom/join') -Filter '*.class'){$common+=@('--class-file',$f.FullName)}
$methods=@('run','identity','parallel','budget','bridge');$programs=@{}
foreach($method in $methods){
    & $Boom @common --method $method --output (Join-Path $root $method) > (Join-Path $root ($method+'-compile.json'))
    if($LASTEXITCODE -ne 0){throw "String join compilation failed: $method"}
    $p=Get-Content (Join-Path $root ($method+'/program.json')) -Raw|ConvertFrom-Json
    if($p.schema -ne 22 -or @($p.interface_dispatch|ForEach-Object{$_.rows}|Where-Object runtime_string).Count -eq 0){throw 'Opaque String callback metadata missing'}
    foreach($row in @($p.interface_dispatch|ForEach-Object{$_.rows}|Where-Object runtime_string)){if($null -ne $row.receiver_class -or $null -ne $row.target){throw 'Runtime String callback pretends to be an executable Java class'}}
    foreach($plan in $p.string_join_plans){if($plan.origin.loader -ne 'bootstrap' -or $plan.origin.source_id -ne 'jdk:java.base'){throw 'String.join origin mismatch'}}
    $programs[$method]=$p;Write-Output "Compiled join/CharSequence entry: $method"
}
$cases=[Collections.Generic.List[object]]::new()
function Bits([int]$n){return ([BitConverter]::ToUInt32([BitConverter]::GetBytes($n),0)).ToString('x')}
function RunCase([int]$mode,[int]$n,[int]$d,[int]$behavior){
    $cases.Add(@{method='run';values=@((Bits $mode),(Bits $n),(Bits $d),(Bits $behavior))})
    $cases.Add(@{method='run';values=@('ffffffff','0','0','0')})
}
foreach($mode in 0..3){foreach($n in @(-1,0,1,2,8,9,17,33)){foreach($d in 0..7){RunCase $mode $n $d 0}}}
foreach($mode in @(4,5)){foreach($d in 0..7){RunCase $mode 0 $d 0}}
foreach($mode in @(1,2)){foreach($n in @(0,1,2,9,17)){foreach($d in @(0,5,6,7)){foreach($behavior in 1..5){RunCase $mode $n $d $behavior}}}}
foreach($n in @(-1,0,1,2)){$cases.Add(@{method='identity';values=@((Bits $n))})}
foreach($n in @(-1,[int]::MinValue,[int]::MaxValue)+@(0..9)){$cases.Add(@{method='bridge';values=@((Bits $n))})}
foreach($n in @(-1,[int]::MinValue,[int]::MaxValue)+@(0..31)){$cases.Add(@{method='parallel';values=@((Bits $n))})}
foreach($n in @(0,1,2,7,8,9,17,33,128)){$cases.Add(@{method='budget';values=@((Bits $n))})}
$lines=@($cases|ForEach-Object{'dev.boom.join.JoinEntry '+$_.method+' '+$programs[$_.method].compilation.descriptor+' '+($_.values -join ' ')})
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Join JVM oracle failed'};$stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Join JVM input stalled'};$oracle.StandardInput.Close()
    if(-not $oracle.WaitForExit(30000)){throw 'Join JVM reference timed out'};if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Join reference count mismatch'}
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '})
    $actual=[BoomNumericProbe]::Run($programs[$method].compilation.dll,(Join-Path $root 'fpstate.dll'),$values,'I',$true)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add(@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
if($failures.Count){$failures|ConvertTo-Json -Depth 8|Set-Content (Join-Path $root 'failures.json');throw "String join mismatches: $($failures.Count), $root"}
Write-Output 'Join and CharSequence JVM/native cases, including callback traces, passed.'
[BoomJoinProbe]::Parallel($programs['parallel'].compilation.dll,(Join-Path $root 'boom-runtime.dll'))
[BoomJoinProbe]::Budget($programs['budget'].compilation.dll,$programs['budget'].entry_id)
$symbols=$programs['run'].symbols
$sequence=@($symbols|Where-Object {$_.class_name -eq 'dev/boom/join/Sequence' -and $_.method -eq 'toString'})[0].id
$next=@($symbols|Where-Object {$_.class_name -eq 'dev/boom/join/Cursor' -and $_.method -eq 'next' -and $_.descriptor -eq '()Ljava/lang/CharSequence;'})[0].id
$hasNext=@($symbols|Where-Object {$_.class_name -eq 'dev/boom/join/Cursor' -and $_.method -eq 'hasNext'})[0].id
[BoomJoinProbe]::Provenance($programs['run'].compilation.dll,$programs['run'].entry_id,$sequence,$next,$hasNext)
$rejections=0
foreach($mode in @('metadata','format')){
    $out=Join-Path $root ('reject-'+$mode)
    if($mode -eq 'metadata'){
        & $Boom compile-program --class-file (Join-Path $classes 'dev/boom/join/JoinEntry.class') --entry-class dev/boom/join/JoinEntry --method parallel --output $out 2>&1|Out-Null
    }else{& $Boom @common --method unsupported --output $out 2>&1|Out-Null}
    if($LASTEXITCODE -eq 0 -or (Test-Path $out)){throw 'Unverified join or unsupported String body accepted'};$rejections++
}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Join compiler changed during verification'}
$report=[ordered]@{backend='boom-string-join-program-v22-masm-x64';compiler_sha256=$sha;runtime_language='assembly';compiled_entries=$methods.Count;differential_cases=$cases.Count;native_executions=($cases.Count*2);multicore_records=6147;workers=8;array_and_iterable_overloads=$true;unicode_NUL_and_surrogates=$true;callback_trace_and_null_order=$true;iterator_and_toString_context_errors=$true;callback_error_provenance=$true;String_to_CharSequence_runtime_bridge=$true;fresh_result_and_intern_identity=$true;vector_growth_above_eight=$true;quiescent_GC_and_small_heap_recovery=$true;temporary_vector_and_result_counts_checked=$true;negative_compile_checks=$rejections;automatic_gc=$false;passed=$true;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText('.boom/latest-join-program.txt',$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
exit 0
