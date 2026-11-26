param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\client.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content -LiteralPath (Join-Path $projectRoot '.boom\latest-jdk-base.txt') -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path $projectRoot ('.boom\assertion-program-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content -LiteralPath $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes (Join-Path $projectRoot 'java\subset\dev\boom\assertions\AssertionEntry.java') (Join-Path $projectRoot 'java\subset\dev\boom\subset\ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Assertion reference javac failed'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
Add-Type -Path (Join-Path $projectRoot 'tests\host\AssertionProbe.cs')
[BoomAssertionProbe]::Abi((Join-Path $root 'boom-runtime.dll'))
$argsList=@('compile-program','--entry-class','dev/boom/assertions/AssertionEntry','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
foreach($file in Get-ChildItem -LiteralPath (Join-Path $classes 'dev\boom\assertions') -Filter '*.class'){$argsList+=@('--class-file',$file.FullName)}
$cases=[Collections.Generic.List[object]]::new()
$selectors=@('ffffffff')+@(0..18|ForEach-Object{$_.ToString('x')})+@('80000000','7fffffff')
foreach($selector in $selectors){$cases.Add([pscustomobject]@{method='query';values=@($selector)})}
foreach($value in @('0','1','2','ffffffff','80000000','7fffffff')){foreach($method in @('actual','cached','noInit')){$cases.Add([pscustomobject]@{method=$method;values=@($value)})}}
$failures=[Collections.Generic.List[object]]::new();$profiles=[Collections.Generic.List[object]]::new();$identities=[Collections.Generic.HashSet[string]]::new()
foreach($mask in 0..3){
    $application=[bool]($mask -band 1);$system=[bool]($mask -band 2)
    $options=@();$jvmOptions=@()
    if($application){$options+='--enable-assertions';$jvmOptions+='-ea'}
    if($system){$options+='--enable-system-assertions';$jvmOptions+='-esa'}
    $programs=@{}
    foreach($method in @('query','actual','cached','noInit')){
        $text=& $Boom @argsList @options --method $method --output (Join-Path $root "policy$mask/$method")
        if($LASTEXITCODE -ne 0){throw "Assertion compilation failed: $mask/$method"}
        $p=$text|ConvertFrom-Json;$programs[$method]=$p
        if($p.schema -ne 13 -or $p.bootstrap_mirror_abi -ne 2 -or $p.assertion_policy.application_enabled -ne $application -or $p.assertion_policy.system_enabled -ne $system){throw 'Assertion profile/ABI contract mismatch'}
        if($method -eq 'noInit' -and @($p.classes|Where-Object name -eq 'dev/boom/assertions/Dormant').Count -ne 0){throw 'Assertion query initialized its target class'}
        if((Get-FileHash -LiteralPath $p.compilation.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $p.compilation.dll_digest.sha256){throw 'Assertion DLL changed'}
        Write-Output "Compiled assertion entry: policy$mask/$method"
    }
    if(-not $identities.Add($programs['query'].input_fingerprint)){throw 'Assertion policies reused a compilation identity'}
    $lines=@($cases|ForEach-Object{(@('dev.boom.assertions.AssertionEntry',$_.method,$programs[$_.method].compilation.descriptor)+@($_.values)) -join ' '})
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in ($jvmOptions+@('-cp',$classes,'dev.boom.subset.ClassNumericOracle'))){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
    try{
        if(-not $oracle.Start()){throw 'Assertion JVM reference failed'}
        $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
        if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Assertion reference input stalled'}
        $oracle.StandardInput.Close();if(-not $oracle.WaitForExit(30000)){throw 'Assertion JVM reference timed out'}
        if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
        $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
    }finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
    if($expected.Count -ne $cases.Count){throw 'Assertion reference record count mismatch'}
    foreach($method in @('query','actual','cached','noInit')){
        $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
        [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '});$p=$programs[$method]
        $actual=[BoomNumericProbe]::Run($p.compilation.dll,(Join-Path $root 'fpstate.dll'),$values,'I',$true)
        for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add([pscustomobject]@{policy=$mask;case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
    }
    $init=@($programs['cached'].classes|Where-Object name -eq 'dev/boom/assertions/Init')[0]
    $counter=@($init.fields|Where-Object name -eq 'count')[0]
    [BoomAssertionProbe]::Cold($programs['cached'].compilation.dll,(Join-Path $root 'boom-runtime.dll'),$init.id,$counter.index,(10+[int]$application))
    $profiles.Add([pscustomobject]@{application_enabled=$application;system_enabled=$system;input_fingerprint=$programs['query'].input_fingerprint;differential_cases=$cases.Count;cold_records=8195;workers=8})
}
$badOutput=Join-Path $root 'reject-unverified-policy'
& $Boom compile-program --class-file (Join-Path $classes 'dev\boom\assertions\AssertionEntry.class') --entry-class dev/boom/assertions/AssertionEntry --method query --enable-assertions --output $badOutput 2>&1|Out-Null
if($LASTEXITCODE -eq 0 -or (Test-Path -LiteralPath $badOutput)){throw 'Unverified assertion configuration was accepted'}
$report=[ordered]@{backend='boom-assertions-program-v13-masm-x64';runtime_language='assembly';mirror_pool_abi=2;assertion_policy_abi=1;profiles=@($profiles.ToArray());compiled_entries=16;differential_cases=$cases.Count*4;native_executions=$cases.Count*8;class_interface_array_and_primitive_mirrors=$true;actual_object_class_identity=$true;null_query_checked=$true;query_does_not_initialize_target=$true;class_initializer_query_cached_once=$true;frozen_startup_policy=$true;per_class_package_overrides=$false;dynamic_classloader_assertion_setters=$false;policy_changes_invalidate_cache=$true;native_abi_and_malformed_policy_checked=$true;multicore_records=32780;workers=8;quiescent_gc_roots=$true;failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 10
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText((Join-Path $projectRoot '.boom\latest-assertion-program.txt'),$root,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1}
