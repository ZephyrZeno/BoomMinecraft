param([string]$Batch='.boom\parallel-compile\server-numeric-v1\report.json',[string]$Lock='.boom\locks\server.json',[string]$Boom='target\release\boom.exe')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
& $Boom verify --lock $Lock|Out-Null
if($LASTEXITCODE -ne 0){throw 'Locked input verification failed.'}
$inputs=Get-Content -LiteralPath $Lock -Raw|ConvertFrom-Json
$batchReport=Get-Content -LiteralPath $Batch -Raw|ConvertFrom-Json
if($batchReport.backend -ne 'boom-numeric-v1-masm-x64' -or $batchReport.input_fingerprint -ne $inputs.fingerprint -or -not $batchReport.assembled){throw 'Batch does not match locked numeric inputs.'}
$methods=@($batchReport.results|Where-Object supported|Where-Object{
    $_.descriptor -match '^\([IJFD]*\)[IJFD]$' -and -not (Get-Content -LiteralPath $_.manifest -Raw|ConvertFrom-Json).requires_heap
})
$root=Join-Path $projectRoot ('.boom\locked-numeric-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$javac=Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe'
& $javac --release 21 -d $classes (Join-Path $projectRoot 'java\subset\dev\boom\subset\ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Locked oracle javac failed.'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
$bits=@{
    I=@('0','1','ffffffff','80000000','7fffffff','12345678','ffff0000','7f0000ff')
    J=@('0','1','ffffffffffffffff','8000000000000000','7fffffffffffffff','0123456789abcdef','fedcba9876543210','00000000ffffffff')
    F=@('0','80000000','3f800000','bf800000','7f800000','ff800000','7fc00000','7f800001','1','7fffff','800000','7f7fffff')
    D=@('0','8000000000000000','3ff0000000000000','bff0000000000000','7ff0000000000000','fff0000000000000','7ff8000000000000','7ff0000000000001','1','000fffffffffffff','0010000000000000','7fefffffffffffff')
}
$cases=[Collections.Generic.List[object]]::new()
for($methodIndex=0;$methodIndex -lt $methods.Count;$methodIndex++){
    $method=$methods[$methodIndex];$close=$method.descriptor.IndexOf(')')
    for($n=0;$n -lt 48;$n++){
        $values=@(for($arg=1;$arg -lt $close;$arg++){
            $set=$bits[[string]$method.descriptor[$arg]]
            # Original 1.21.1 fwh.a repeatedly adds/subtracts 2*pi. Infinite
            # or enormous angles do not converge on the JVM either. Exercise
            # a bounded angle domain; do not modify the compiled algorithm.
            if($method.class -eq 'fwh' -and $method.method -eq 'a' -and $method.descriptor -eq '(FFF)F'){$set=@('0','80000000','3f800000','bf800000','40490fdb','c0490fdb','40c90fdb','c0c90fdb','42000000','c2000000')}
            $set[($n+$arg*($n%5))%$set.Count]
        })
        $cases.Add([pscustomobject]@{method_index=$methodIndex;class=$method.class;method=$method.method;descriptor=$method.descriptor;values=$values})
    }
}
$paths=@($classes)+@($inputs.classpath|ForEach-Object{$id=$_;($inputs.files|Where-Object id -eq $id).path})
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',($paths -join [IO.Path]::PathSeparator),'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Cannot start locked JVM oracle.'}
    $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    $lines=@($cases|ForEach-Object{(@($_.class,$_.method,$_.descriptor)+@($_.values)-join ' ').TrimEnd()})
    $write=$oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n")
    if(-not $write.Wait(15000)){$oracle.Kill($true);$oracle.WaitForExit();throw 'Locked oracle input stalled or a method failed to terminate.'}
    $oracle.StandardInput.Close()
    if(-not $oracle.WaitForExit(30000)){$oracle.Kill($true);$oracle.WaitForExit();throw 'Locked JVM oracle timed out.'}
    if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Locked oracle result count mismatch.'}
$failures=[Collections.Generic.List[object]]::new()
for($methodIndex=0;$methodIndex -lt $methods.Count;$methodIndex++){
    $method=$methods[$methodIndex];$manifest=Get-Content -LiteralPath $method.manifest -Raw|ConvertFrom-Json
    if((Get-FileHash -LiteralPath $manifest.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.dll_digest.sha256){throw 'Locked numeric DLL hash mismatch.'}
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method_index -eq $methodIndex){$i}})
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '})
    $actual=[BoomNumericProbe]::Run($manifest.dll,(Join-Path $root 'fpstate.dll'),$values,[char]$method.descriptor[-1])
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add([pscustomobject]@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
$report=[ordered]@{backend=$batchReport.backend;input_fingerprint=$inputs.fingerprint;locked_methods=$methods.Count;differential_cases=$cases.Count;native_executions=$cases.Count*2;bounded_domains=@{'fwh.a(FFF)F'='finite angles |value| <= 32; infinite/huge inputs may not terminate in original JVM code'};caller_fp_state_checked=$true;failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1};exit 0
