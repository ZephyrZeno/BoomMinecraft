param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\client.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$compilerSha=(Get-FileHash -LiteralPath $Boom).Hash.ToLowerInvariant()
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content -LiteralPath (Join-Path $projectRoot '.boom\latest-jdk-base.txt') -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path $projectRoot ('.boom\clock-program-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content -LiteralPath $MetadataLock -Raw|ConvertFrom-Json
$base=Get-Content -LiteralPath $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes (Join-Path $projectRoot 'java\subset\dev\boom\vmclock\ClockEntry.java') (Join-Path $projectRoot 'java\subset\dev\boom\subset\ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Clock reference javac failed'}
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
Add-Type -Path (Join-Path $projectRoot 'tests\host\ClockProbe.cs')
$mod=[System.Numerics.BigInteger]::Pow(2,64)
function BigHex([string]$s){return [System.Numerics.BigInteger]::Parse(('0'+$s),[Globalization.NumberStyles]::AllowHexSpecifier)}
function Hex64([System.Numerics.BigInteger]$value){$value=[System.Numerics.BigInteger]::Remainder($value,$mod);if($value.Sign -lt 0){$value=[System.Numerics.BigInteger]::Add($value,$mod)};$hex=$value.ToString('x').TrimStart('0');if(-not $hex){$hex='0'};return $hex}
$filetimes=[Collections.Generic.List[string]]::new();$counters=[Collections.Generic.List[string]]::new()
$epoch=[System.Numerics.BigInteger]::Parse('116444736000000000')
foreach($value in @([System.Numerics.BigInteger]0,[System.Numerics.BigInteger]1,($epoch-10001),($epoch-10000),($epoch-1),$epoch,($epoch+1),($epoch+9999),($epoch+10000),(BigHex '7fffffffffffffff'),(BigHex 'ffffffffffffffff'))){
    $expected=[System.Numerics.BigInteger]::Divide($value,10000)-[System.Numerics.BigInteger]::Parse('11644473600000')
    $filetimes.Add((Hex64 $value)+' '+(Hex64 $expected))
}
$frequencies=@('1','3','989680','3b9aca00','2540be401','7fffffffffffffff','ffffffffffffffff')
$counts=@('0','1','2','98967f','989680','123456789abcdef0','8000000000000000','ffffffffffffffff')
foreach($a in $counts){foreach($b in $frequencies){$expected=[System.Numerics.BigInteger]::Divide([System.Numerics.BigInteger]::Multiply((BigHex $a),1000000000),(BigHex $b));$counters.Add($a+' '+$b+' '+(Hex64 $expected))}}
$seed=BigHex '123456789abcdef0'
for($i=0;$i -lt 256;$i++){
    $seed=[System.Numerics.BigInteger]::Remainder(($seed*6364136223846793005+[System.Numerics.BigInteger]1442695040888963407),$mod)
    $frequency=[System.Numerics.BigInteger]::Remainder(($seed*17+1),($mod-1))+1
    $expected=[System.Numerics.BigInteger]::Divide([System.Numerics.BigInteger]::Multiply($seed,1000000000),$frequency)
    $counters.Add((Hex64 $seed)+' '+(Hex64 $frequency)+' '+(Hex64 $expected))
}
[IO.File]::WriteAllText((Join-Path $root 'arithmetic-vectors.json'),([ordered]@{filetime=@($filetimes.ToArray());counter=@($counters.ToArray());oracle='BigInteger direct product/division, modulo 2^64'}|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))
[BoomClockProbe]::Arithmetic((Join-Path $root 'boom-runtime.dll'),$filetimes.ToArray(),$counters.ToArray())
$programs=@{};$methods=@('millis','nanos','monotonic','elapsed')
foreach($method in $methods){
    $text=& $Boom compile-program --class-file (Join-Path $classes 'dev\boom\vmclock\ClockEntry.class') --entry-class dev/boom/vmclock/ClockEntry --method $method --metadata-lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root $method) --assemble
    if($LASTEXITCODE -ne 0){throw "Clock compilation failed: $method"}
    $p=$text|ConvertFrom-Json;$programs[$method]=$p
    $binding=@($p.vm_bindings)[0]
    if($p.schema -ne 14 -or @($p.vm_bindings).Count -ne 1 -or $binding.owner -ne 'java/lang/System' -or $binding.origin.loader -ne 'bootstrap' -or $binding.origin.source_id -ne 'jdk:java.base' -or $binding.origin.sha256 -ne $base.classes.'java.lang.System'.sha256){throw 'VM clock binding lost its pinned native origin'}
    if(@($p.classes|Where-Object name -eq 'java/lang/System').Count -ne 0){throw 'Clock intrinsic unexpectedly generated the unfinished System Java bootstrap'}
    if((Get-FileHash -LiteralPath $p.compilation.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $p.compilation.dll_digest.sha256){throw 'Clock DLL changed'}
    [BoomClockProbe]::Samples($p.compilation.dll,[array]::IndexOf($methods,$method))
    Write-Output "Clock samples passed: $method"
}
[BoomClockProbe]::Parallel($programs['monotonic'].compilation.dll,(Join-Path $root 'boom-runtime.dll'))
# A deterministic property, rather than timestamps sampled at different instants,
# can also be compared directly with the pinned JVM.
$values=@('0','1','2','10','80','400','8000','ffffffff')
$lines=@($values|ForEach-Object{'dev.boom.vmclock.ClockEntry monotonic (I)J '+$_})
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Clock JVM reference failed'}
    $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    $oracle.StandardInput.WriteLine(($lines -join "`n"));$oracle.StandardInput.Close();if(-not $oracle.WaitForExit(30000)){throw 'Clock JVM reference timed out'}
    if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $reference=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
    if($reference.Count -ne $values.Count -or @($reference|Where-Object {$_ -ne 'v 0000000000000001'}).Count -ne 0){throw 'JVM clock property mismatch'}
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
$actual=[BoomNumericProbe]::Run($programs['monotonic'].compilation.dll,(Join-Path $root 'fpstate.dll'),[string[]]$values,'J',$true)
for($i=0;$i -lt $values.Count;$i++){if($actual[$i] -ne $reference[$i]){throw 'Generated clock property differs from JVM'}}
$report=[ordered]@{backend='boom-vm-program-v14-masm-x64';runtime_language='assembly';compiled_entries=4;pinned_native_System_binding=$true;current_time_millis=$true;nano_time=$true;utc_sample_checks=1000;qpc_interval_checks=1000;generated_monotonic_checks=1000;generated_elapsed_checks=1000;filetime_arithmetic_vectors=$filetimes.Count;counter_arithmetic_vectors=$counters.Count;arithmetic_oracle='BigInteger direct formula';jvm_deterministic_property_cases=$values.Count;full_64bit_conversion_and_wrap=$true;pre_1970_flooring=$true;multicore_records=8195;workers=8;clock_guest_heap_allocations=0;System_java_bootstrap_complete=$false;full_game_ready=$false;passed=$true;run_directory=$root}
if((Get-FileHash -LiteralPath $Boom).Hash.ToLowerInvariant() -ne $compilerSha){throw 'Clock compiler changed during verification'}
$report['compiler_sha256']=$compilerSha
$json=$report|ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText((Join-Path $projectRoot '.boom\latest-clock-program.txt'),$root,[Text.UTF8Encoding]::new($false));Write-Output $json
