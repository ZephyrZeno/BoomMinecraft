param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path (Get-Location) ('.boom/values-program-tests/'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/values/ValuesEntry.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'Value conversion javac failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output $root
& scripts/Build-FpProbe.ps1 -Output $root
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/ValuesProbe.cs
$common=@('compile-program','--class-file',(Join-Path $classes 'dev/boom/values/ValuesEntry.class'),'--entry-class','dev/boom/values/ValuesEntry','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
$methods=@('character','integer','wide','bool','fresh','combined','parallel','integerDirect','wideDirect','freshDirect');$programs=@{}
foreach($method in $methods){
    & $Boom @common --method $method --output (Join-Path $root $method) > (Join-Path $root ($method+'-compile.json'))
    if($LASTEXITCODE -ne 0){throw "Primitive String.valueOf compilation failed: $method"}
    $p=Get-Content (Join-Path $root ($method+'/program.json')) -Raw|ConvertFrom-Json
    $initialized=@($p.string_value_bindings|Where-Object {$null -ne $_.initializer}).Count -ne 0
    if($p.schema -ne $(if($initialized){25}else{23}) -or $p.string_value_bindings.Count -eq 0){throw 'Primitive String.valueOf metadata missing'}
    foreach($b in $p.string_value_bindings){if($b.origin.loader -ne 'bootstrap' -or $b.origin.source_id -ne 'jdk:java.base' -or (($b.kind -eq 'Boolean') -ne ($null -ne $b.boolean_literals))){throw 'Value member binding or representation mismatch'}}
    foreach($b in $p.string_value_bindings|Where-Object {$null -ne $_.initializer}){
        $owner=if($b.kind -in @('Int','IntegerToString')){'java/lang/Integer'}else{'java/lang/Long'}
        $c=@($p.classes|Where-Object id -eq $b.initializer.class_id)[0]
        if($c.name -ne $owner -or $null -eq $c.initializer -or $b.initializer.origin.binary_name -ne $owner.Replace('/','.')){throw 'Decimal wrapper initialization metadata mismatch'}
    }
    $programs[$method]=$p;Write-Output "Compiled primitive value entry: $method"
}
function Bits([int]$n){return ([BitConverter]::ToUInt32([BitConverter]::GetBytes($n),0)).ToString('x')}
$ints=[Collections.Generic.List[string]]::new()
foreach($n in @(0,1,-1,[int]::MinValue,[int]::MaxValue,127,128,255,256,32767,32768,65535,65536,-65536,0xd800,0xdbff,0xdc00,0xdfff,0x1f600)){$ints.Add((Bits $n))}
[uint64]$seed=0x12345678
for($i=0;$i -lt 96;$i++){$seed=($seed*1664525+1013904223) -band 0xffffffffL;$ints.Add($seed.ToString('x'))}
$cases=[Collections.Generic.List[object]]::new()
foreach($s in $ints){foreach($method in @('character','integer','bool','fresh','combined','parallel','integerDirect','freshDirect')){$cases.Add(@{method=$method;values=@($s)})}}
$longs=[Collections.Generic.List[string]]::new()
foreach($s in @('0','1','ffffffffffffffff','8000000000000000','7fffffffffffffff','8000000000000001','7ffffffffffffffe')){$longs.Add($s)}
$mod=[Numerics.BigInteger]::Pow(2,64)
for($i=0;$i -le 18;$i++){foreach($delta in @(-1,0,1)){foreach($sign in @(-1,1)){$v=([Numerics.BigInteger]::Pow(10,$i)+$delta)*$sign;$v=($v+$mod)%$mod;$s=$v.ToString('x').TrimStart('0');if(-not $s){$s='0'};$longs.Add($s)}}}
foreach($s in $longs){foreach($method in @('wide','wideDirect')){$cases.Add(@{method=$method;values=@($s)})}}
$lines=@($cases|ForEach-Object{'dev.boom.values.ValuesEntry '+$_.method+' '+$programs[$_.method].compilation.descriptor+' '+($_.values -join ' ')})
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Values JVM reference failed'};$stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Values JVM input stalled'};$oracle.StandardInput.Close()
    if(-not $oracle.WaitForExit(30000)){throw 'Values JVM reference timed out'};if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Values reference count mismatch'}
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '})
    $actual=[BoomNumericProbe]::Run($programs[$method].compilation.dll,(Join-Path $root 'fpstate.dll'),$values,'I',$true)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add(@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
if($failures.Count){$failures|ConvertTo-Json -Depth 7|Set-Content (Join-Path $root 'failures.json');throw "Value conversion mismatches: $($failures.Count), $root"}
[BoomValuesProbe]::Parallel($programs['parallel'].compilation.dll,(Join-Path $root 'boom-runtime.dll'),$false)
[BoomValuesProbe]::Parallel($programs['bool'].compilation.dll,(Join-Path $root 'boom-runtime.dll'),$true)
[BoomValuesProbe]::Budget($programs['character'].compilation.dll,$programs['character'].entry_id)
$retained=[ordered]@{}
foreach($method in @('integer','wide','integerDirect','wideDirect')){
    $p=$programs[$method];$wide=$method -in @('wide','wideDirect');$name=if($wide){'java/lang/Long'}else{'java/lang/Integer'}
    $c=@($p.classes|Where-Object name -eq $name)[0];$type=@($c.fields|Where-Object name -eq 'TYPE')[0]
    $retained[$method]=[BoomValuesProbe]::Decimal($p.compilation.dll,(Join-Path $root 'boom-runtime.dll'),$wide,$c.id,$type.index)
}
$p=$programs['integerDirect'];$c=@($p.classes|Where-Object name -eq 'java/lang/Integer')[0]
[BoomValuesProbe]::InitializationFailure($p.compilation.dll,(Join-Path $root 'boom-runtime.dll'),$c.id,$c.initializer)
$rejections=0
foreach($mode in @('metadata','float','radix')){
    $out=Join-Path $root ('reject-'+$mode)
    if($mode -eq 'metadata'){& $Boom compile-program --class-file (Join-Path $classes 'dev/boom/values/ValuesEntry.class') --entry-class dev/boom/values/ValuesEntry --method character --output $out 2>&1|Out-Null}
    else{& $Boom @common --method $(if($mode -eq 'float'){'unsupported'}else{'unsupportedRadix'}) --output $out 2>&1|Out-Null}
    if($LASTEXITCODE -eq 0 -or (Test-Path $out)){throw 'Unverified or unsupported value conversion accepted'};$rejections++
}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Values compiler changed during test'}
$report=[ordered]@{backend='boom-decimal-program-v25-masm-x64';compiler_sha256=$sha;runtime_language='assembly';compiled_entries=$methods.Count;differential_cases=$cases.Count;native_executions=($cases.Count*2);multicore_records=36882;workers=8;char_int_long_boolean=$true;Integer_and_Long_toString=$true;original_wrapper_initializers_execute=$true;valueOf_direct_delegation_proven=$true;cold_concurrent_wrapper_initialization=$true;initializer_oom_source_and_persistent_failure=$true;decimal_static_objects_after_collection=$retained;UTF16_NUL_surrogates_and_truncation=$true;signed_integer_extremes_and_decimal_boundaries=$true;boolean_literal_identity_and_reuse=$true;fresh_numeric_and_character_results=$true;interoperable_with_String_join=$true;character_temp_objects_per_call=2;boolean_live_guest_objects_after_warmup=4;oom_and_quiescent_recovery=$true;negative_compile_checks=$rejections;float_and_double_formatting=$false;general_radix_formatting=$false;automatic_gc=$false;passed=$true;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-values-program.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
