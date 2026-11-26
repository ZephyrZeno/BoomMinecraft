param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\client.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content -LiteralPath (Join-Path $projectRoot '.boom\latest-jdk-base.txt') -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path $projectRoot ('.boom\bootstrap-program-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content -LiteralPath $MetadataLock -Raw|ConvertFrom-Json
$base=Get-Content -LiteralPath $JdkBase -Raw|ConvertFrom-Json
& (Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes (Join-Path $projectRoot 'java\subset\dev\boom\bootstrap\BootstrapEntry.java') (Join-Path $projectRoot 'java\subset\dev\boom\subset\ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Bootstrap reference javac failed'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
$argsList=@('compile-program','--entry-class','dev/boom/bootstrap/BootstrapEntry','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
foreach($file in Get-ChildItem -LiteralPath (Join-Path $classes 'dev\boom\bootstrap') -Filter '*.class'){$argsList+=@('--class-file',$file.FullName)}
$programs=@{};$expectedClass=@{nullChecks='java/util/Objects';optionalInt='java/util/OptionalInt';optionalLong='java/util/OptionalLong';optionalDouble='java/util/OptionalDouble';retained='java/util/OptionalInt'}
foreach($method in @('nullChecks','optionalInt','optionalLong','optionalDouble','retained')){
    $text=& $Boom @argsList --method $method --output (Join-Path $root $method)
    if($LASTEXITCODE -ne 0){throw "Bootstrap compilation failed: $method"}
    $p=$text|ConvertFrom-Json;$programs[$method]=$p
    if($p.schema -ne 11 -or $p.compilation.abi -ne 'context16-argv64-rax64-v1' -or $expectedClass[$method] -notin $p.symbols.class_name){throw 'Expected original JDK executable body is absent'}
    foreach($source in @($p.sources|Where-Object origin)){
        if($source.origin.loader -ne 'bootstrap' -or $source.origin.source_id -ne 'jdk:java.base' -or $source.digest.sha256 -ne $source.origin.sha256){throw 'Bootstrap source lost its verified defining-loader origin'}
        $proof=$base.classes.PSObject.Properties[$source.class_name.Replace('/','.')].Value
        if($proof.sha256 -ne $source.digest.sha256 -or (Get-FileHash -LiteralPath $source.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $proof.sha256){throw 'JDK bytecode differs from locked java.base'}
    }
    if($method -in @('optionalInt','optionalLong','optionalDouble')){
        $layout=@($p.object_layouts|Where-Object class_name -eq $expectedClass[$method])[0].layout
        $bytes=if($method -eq 'optionalInt'){5}else{9}
        if($layout.abi -ne 2 -or $layout.payload_bytes -ne $bytes -or $layout.reference_prefix_fields -ne 0){throw 'JDK compact layout mismatch'}
    }
    Write-Output "Compiled pinned JDK entry: $method"
}
$cases=[Collections.Generic.List[object]]::new()
$ints=@('0','1','2','ffffffff','80000000','7fffffff','12345678','abcdef01')
foreach($value in $ints){$cases.Add([pscustomobject]@{method='nullChecks';values=@($value)});foreach($fallback in $ints){$cases.Add([pscustomobject]@{method='optionalInt';values=@($value,$fallback)})}}
$longs=@('0','1','2','ffffffffffffffff','8000000000000000','7fffffffffffffff','123456789abcdef0','abcdef0123456789')
foreach($value in $longs){foreach($fallback in $longs){$cases.Add([pscustomobject]@{method='optionalLong';values=@($value,$fallback)})}}
$doubles=@('0','8000000000000000','3ff0000000000000','7ff0000000000000','fff0000000000000','7ff8000000000001','7ff0000000000001','1','fffffffffffff','0010000000000000','7fefffffffffffff')
foreach($value in $doubles){foreach($fallback in $doubles){foreach($present in @('0','1','ffffffff')){$cases.Add([pscustomobject]@{method='optionalDouble';values=@($value,$fallback,$present)})}}}
$lines=@($cases|ForEach-Object{(@('dev.boom.bootstrap.BootstrapEntry',$_.method,$programs[$_.method].compilation.descriptor)+@($_.values)) -join ' '})
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Bootstrap JVM reference failed'}
    $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Bootstrap reference input stalled'}
    $oracle.StandardInput.Close();if(-not $oracle.WaitForExit(30000)){throw 'Bootstrap JVM reference timed out'}
    if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Bootstrap reference record count mismatch'}
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
$failures=[Collections.Generic.List[object]]::new()
foreach($method in @('nullChecks','optionalInt','optionalLong','optionalDouble')){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '});$m=$programs[$method].compilation
    if((Get-FileHash -LiteralPath $m.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $m.dll_digest.sha256){throw 'Bootstrap native DLL changed'}
    $actual=[BoomNumericProbe]::Run($m.dll,(Join-Path $root 'fpstate.dll'),$values,[char]$m.descriptor[-1],$true)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add([pscustomobject]@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
Add-Type -Path (Join-Path $projectRoot 'tests\host\BootstrapProbe.cs')
[BoomBootstrapProbe]::Cold($programs['optionalInt'].compilation.dll,(Join-Path $root 'boom-runtime.dll'))
[BoomBootstrapProbe]::Retained($programs['retained'].compilation.dll)
# A pinned bootstrap class is still forbidden as an explicit replacement.
$jdkSource=@($programs['nullChecks'].sources|Where-Object class_name -eq 'java/util/Objects')[0].path
$badOutput=Join-Path $root 'reject-explicit-bootstrap'
& $Boom compile-program --class-file $jdkSource --entry-class java/util/Objects --method nonNull --output $badOutput --assemble 2>&1|Out-Null
if($LASTEXITCODE -eq 0 -or (Test-Path -LiteralPath $badOutput)){throw 'Explicit bootstrap replacement accepted'}
$report=[ordered]@{backend='boom-bootstrap-program-v11-masm-x64';runtime_language='assembly';compiled_entries=5;pinned_jdk_java_bodies=$true;bootstrap_application_loader_identity=$true;private_jdk_fields_and_constructors=$true;compact_payload_bytes=@{OptionalInt=5;OptionalLong=9;OptionalDouble=9};differential_cases=$cases.Count;native_executions=$cases.Count*2;cold_records=8195;workers=8;static_singleton_once=$true;cross_loader_static_gc_roots=$true;explicit_bootstrap_redefinition_rejected=$true;throwable_codegen_integrated=$false;failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $projectRoot '.boom\latest-bootstrap-program.txt'),$root,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1}
