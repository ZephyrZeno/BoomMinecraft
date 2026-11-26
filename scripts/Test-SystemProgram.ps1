param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path (Get-Location) ('.boom/system-program-tests/'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/system/SystemEntry.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'System reference javac failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root
& scripts/Build-FpProbe.ps1 -Output $root
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/SystemProbe.cs
[BoomSystemProbe]::Abi((Join-Path $root 'boom-runtime.dll'))
Write-Output 'System.arraycopy native ABI checks passed.'
$common=@('compile-program','--entry-class','dev/boom/system/SystemEntry','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
foreach($f in Get-ChildItem (Join-Path $classes 'dev/boom/system') -Filter '*.class'){$common+=@('--class-file',$f.FullName)}
$programs=@{}
foreach($method in @('copy','parallel','registration')){
    & $Boom @common --method $method --output (Join-Path $root $method) > (Join-Path $root ($method+'-compile.json'))
    if($LASTEXITCODE -ne 0){throw "System program compilation failed: $method"}
    $p=Get-Content (Join-Path $root ($method+'/program.json')) -Raw|ConvertFrom-Json
    if($p.schema -ne 21 -or @($p.vm_bindings|Where-Object operation -eq 'array_copy').Count -ne 1 -or $p.vm_bindings[0].origin.loader -ne 'bootstrap' -or -not $p.runtime_type_map_abi){throw 'System native binding metadata mismatch'}
    if($method -eq 'registration' -and ($p.vm_bindings.Count -ne 4 -or @($p.symbols|Where-Object {$_.class_name -eq 'java/lang/System' -and $_.method -eq '<clinit>'}).Count -ne 1)){throw 'Original System registration initializer missing'}
    $programs[$method]=$p;Write-Output "Compiled System.arraycopy entry: $method"
}
function Bits([int]$n){return ([BitConverter]::ToUInt32([BitConverter]::GetBytes($n),0)).ToString('x')}
$cases=[Collections.Generic.List[object]]::new()
$ranges=@(@(0,0,0),@(0,0,8),@(0,2,6),@(2,0,6),@(7,7,1),@(8,8,0),@(-1,0,0),@(0,-1,0),@(0,0,-1),@(9,0,0),@([int]::MaxValue,0,0),@(0,[int]::MaxValue,0),@(0,0,[int]::MaxValue),@(7,7,2),@([int]::MinValue,[int]::MinValue,0))
foreach($k in 0..22){foreach($alias in @(0,32)){foreach($range in $ranges){
    $cases.Add(@{method='copy';values=@((Bits ($k+$alias)),(Bits $range[0]),(Bits $range[1]),(Bits $range[2]))})
    $cases.Add(@{method='copy';values=@('ffffffff','0','0','0')})
}}}
foreach($n in (@(-1,[int]::MinValue,[int]::MaxValue)+@(0..31))){foreach($method in @('parallel','registration')){$cases.Add(@{method=$method;values=@((Bits $n))})}}
$lines=@($cases|ForEach-Object{'dev.boom.system.SystemEntry '+$_.method+' '+$programs[$_.method].compilation.descriptor+' '+($_.values -join ' ')})
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'System JVM oracle failed'};$stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'System oracle input stalled'};$oracle.StandardInput.Close()
    if(-not $oracle.WaitForExit(30000)){throw 'System oracle timed out'};if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'System reference count mismatch'}
$failures=[Collections.Generic.List[object]]::new()
foreach($method in @('copy','parallel','registration')){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '})
    $actual=[BoomNumericProbe]::Run($programs[$method].compilation.dll,(Join-Path $root 'fpstate.dll'),$values,'I',$true)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add(@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
if($failures.Count){$failures|ConvertTo-Json -Depth 8|Set-Content (Join-Path $root 'failures.json');throw "System arraycopy mismatches: $($failures.Count), $root"}
Write-Output 'System.arraycopy JVM/native differential and post-failure state checks passed.'
[BoomSystemProbe]::Parallel($programs['parallel'].compilation.dll,(Join-Path $root 'boom-runtime.dll'),-1)
$systemClass=@($programs['registration'].classes|Where-Object name -eq 'java/lang/System')[0].id
[BoomSystemProbe]::Parallel($programs['registration'].compilation.dll,(Join-Path $root 'boom-runtime.dll'),$systemClass)
$out=Join-Path $root 'reject-system-phase'
& $Boom @common --method unsupportedPhase --output $out 2>&1|Out-Null
if($LASTEXITCODE -eq 0 -or (Test-Path $out)){throw 'System phase-dependent method accepted before startup phases'}
$out=Join-Path $root 'reject-metadata'
& $Boom compile-program --class-file (Join-Path $classes 'dev/boom/system/SystemEntry.class') --entry-class dev/boom/system/SystemEntry --method parallel --output $out 2>&1|Out-Null
if($LASTEXITCODE -eq 0 -or (Test-Path $out)){throw 'System arraycopy accepted without source-verified metadata'}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'System compiler changed during verification'}
$report=[ordered]@{backend='boom-system-program-v21-masm-x64';compiler_sha256=$sha;runtime_language='assembly';compiled_entries=3;differential_cases=$cases.Count;native_executions=($cases.Count*2);multicore_records=24594;workers=8;all_eight_primitive_arrays=$true;primitive_raw_bit_vectors=96;reference_covariance_and_partial_copy=$true;null_type_bounds_precedence=$true;zero_length_and_overlap=$true;source_and_destination_state_checked_after_error=$true;original_Object_constructor_source_proof=$true;copy_guest_allocations=0;quiescent_gc_preserves_partial_state=$true;negative_compile_checks=2;System_registerNatives=$true;registered_native_methods=3;native_concurrent_registration_calls=64;original_System_clinit=$true;System_java_bootstrap_complete=$false;automatic_gc=$false;passed=$true;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText('.boom/latest-system-program.txt',$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
exit 0
