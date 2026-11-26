param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path (Get-Location) ('.boom/primitive-program-tests/'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/primitives/PrimitiveEntry.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'Primitive javac reference failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root
& scripts/Build-FpProbe.ps1 -Output $root
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/PrimitiveProbe.cs
[BoomPrimitiveProbe]::Abi((Join-Path $root 'boom-runtime.dll'))
Write-Output 'Primitive native ABI checks passed.'
$programs=@{};$methods=@('name','identity','traits','assignable','parallel')
foreach($method in $methods){
    $out=Join-Path $root $method
    & $Boom compile-program --class-file (Join-Path $classes 'dev/boom/primitives/PrimitiveEntry.class') --entry-class dev/boom/primitives/PrimitiveEntry --method $method --metadata-lock $MetadataLock --jdk-base $JdkBase --output $out --assemble > (Join-Path $root ($method+'-compile.json'))
    if($LASTEXITCODE -ne 0){throw "Primitive compilation failed: $method"}
    $p=Get-Content (Join-Path $out 'program.json') -Raw|ConvertFrom-Json
    if($p.schema -ne 20 -or $p.primitive_class_bindings.Count -ne 9 -or @($p.mirror_types|Where-Object {$_.kind -eq 'primitive' -and $_.value -eq 'Void'}).Count -ne 1){throw 'Primitive native metadata contract mismatch'}
    foreach($b in $p.primitive_class_bindings){if($b.caller.loader -ne 'bootstrap' -or $b.caller.source_id -ne 'jdk:java.base' -or $b.type_ids.Count -ne 9){throw 'Unverified primitive caller'}}
    $programs[$method]=$p;Write-Output "Compiled original JDK wrapper TYPE entry: $method"
}
$cases=[Collections.Generic.List[object]]::new()
function Bits([int]$n){return ([BitConverter]::ToUInt32([BitConverter]::GetBytes($n),0)).ToString('x')}
foreach($n in (@(0..31)+@(-1,[int]::MinValue,[int]::MaxValue))){foreach($method in @('name','identity','traits','parallel')){$cases.Add(@{method=$method;values=@((Bits $n))})}}
foreach($a in 0..15){foreach($b in 0..15){$cases.Add(@{method='assignable';values=@((Bits $a),(Bits $b))})}}
$lines=@($cases|ForEach-Object{'dev.boom.primitives.PrimitiveEntry '+$_.method+' '+$programs[$_.method].compilation.descriptor+' '+($_.values -join ' ')})
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Primitive JVM reference failed'};$stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Primitive oracle input stalled'};$oracle.StandardInput.Close()
    if(-not $oracle.WaitForExit(30000)){throw 'Primitive oracle timed out'};if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Primitive reference count mismatch'}
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '})
    $actual=[BoomNumericProbe]::Run($programs[$method].compilation.dll,(Join-Path $root 'fpstate.dll'),$values,'I',$true)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add(@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
if($failures.Count){$failures|ConvertTo-Json -Depth 8|Set-Content (Join-Path $root 'failures.json');throw "Primitive mismatches: $($failures.Count), $root"}
[BoomPrimitiveProbe]::Parallel($programs['parallel'].compilation.dll,(Join-Path $root 'boom-runtime.dll'))
$out=Join-Path $root 'reject-metadata'
& $Boom compile-program --class-file (Join-Path $classes 'dev/boom/primitives/PrimitiveEntry.class') --entry-class dev/boom/primitives/PrimitiveEntry --method name --output $out 2>&1|Out-Null
if($LASTEXITCODE -eq 0 -or (Test-Path $out)){throw 'Primitive wrapper execution accepted without verified metadata'}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Primitive compiler changed during validation'}
$report=[ordered]@{backend='boom-primitive-class-program-v20-masm-x64';compiler_sha256=$sha;runtime_language='assembly';compiled_entries=$methods.Count;primitive_types=9;original_jdk_wrapper_initializers=$true;differential_cases=$cases.Count;native_executions=($cases.Count*2);multicore_records=9225;workers=8;shared_component_mirror_identity=$true;void_mirror=$true;null_and_unknown_name_abi_checked=$true;invalid_pool_and_type_ids_rejected=$true;quiescent_gc_preserves_identities=$true;negative_compile_checks=1;full_reflection=$false;automatic_gc=$false;passed=$true;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText('.boom/latest-primitive-program.txt',$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
exit 0
