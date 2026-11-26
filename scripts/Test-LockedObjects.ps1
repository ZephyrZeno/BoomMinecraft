param([string]$Batch='.boom\parallel-compile\client-objects-v1\report.json',[string]$Lock='.boom\locks\client.json',[string]$Boom='target\release\boom.exe')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
& $Boom verify --lock $Lock|Out-Null
if($LASTEXITCODE -ne 0){throw 'Locked client inputs failed verification.'}
$inputs=Get-Content -LiteralPath $Lock -Raw|ConvertFrom-Json
$batchReport=Get-Content -LiteralPath $Batch -Raw|ConvertFrom-Json
if($batchReport.input_fingerprint -ne $inputs.fingerprint -or -not $batchReport.assembled){throw 'Batch identity mismatch.'}
$root=Join-Path $projectRoot ('.boom\locked-object-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$paths=@($inputs.classpath|ForEach-Object{$id=$_;($inputs.files|Where-Object id -eq $id).path})
$javac=Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe'
& $javac --release 21 -proc:none -cp ($paths -join ';') -d $classes (Join-Path $projectRoot 'java\subset\dev\boom\subset\RangeObjectOracle.java')
if($LASTEXITCODE -ne 0){throw 'Actual object oracle javac failed.'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
$manifests=@{}
foreach($method in @('at','between')){
    $matches=@($batchReport.results|Where-Object { $_.supported -and $_.class -eq 'com.mojang.brigadier.context.StringRange' -and $_.method -eq $method })
    if($matches.Count -ne 1){throw 'Expected exact actual factory selection.'}
    $previous=Get-Content -LiteralPath $matches[0].manifest -Raw|ConvertFrom-Json
    if((Get-FileHash -LiteralPath $previous.source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $previous.source_digest.sha256){throw 'Extracted class identity mismatch.'}
    $text=& $Boom compile-managed --class-file $previous.source --method $method --descriptor $matches[0].descriptor --output (Join-Path $root $method) --assemble
    if($LASTEXITCODE -ne 0){throw 'Actual factory compilation failed.'}
    $manifests[$method]=$text|ConvertFrom-Json
}
$bits=@('0','1','ffffffff','80000000','7fffffff','12345678','ffff0000','7f0000ff','a','fffffff6','8001','ffff7fff')
$cases=[Collections.Generic.List[object]]::new()
foreach($start in $bits){$cases.Add([pscustomobject]@{method='at';values=@($start)});foreach($end in $bits){$cases.Add([pscustomobject]@{method='between';values=@($start,$end)})}}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',((@($classes)+$paths) -join ';'),'dev.boom.subset.RangeObjectOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Cannot start actual object JVM oracle.'}
    $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    $lines=@($cases|ForEach-Object{(@($_.method)+@($_.values)) -join ' '})
    if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Actual object oracle input stalled.'}
    $oracle.StandardInput.Close()
    if(-not $oracle.WaitForExit(30000)){throw 'Actual object oracle timed out.'}
    if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Actual object oracle count mismatch.'}
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
$failures=[Collections.Generic.List[object]]::new()
foreach($method in @('at','between')){
    $manifest=$manifests[$method];$layout=$manifest.object_layout
    if($layout.abi -ne 1 -or $layout.reference_prefix_fields -ne 0 -or $layout.fields.Count -ne 2){throw 'Unexpected actual StringRange layout.'}
    [int[]]$offsets=@(foreach($name in @('start','end')){$field=@($layout.fields|Where-Object name -eq $name);if($field.Count -ne 1 -or $field[0].descriptor -ne 'I'){throw 'Unexpected actual StringRange field.'};$field[0].offset})
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '})
    $actual=[BoomNumericProbe]::InspectIntObject($manifest.dll,(Join-Path $root 'fpstate.dll'),$values,$offsets)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add([pscustomobject]@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
$report=[ordered]@{backend='boom-numeric-v1-masm-x64';runtime_language='assembly';input_fingerprint=$inputs.fingerprint;class='com.mojang.brigadier.context.StringRange';compiled_factories=2;differential_cases=$cases.Count;native_executions=$cases.Count*2;actual_locked_class=$true;constructor_and_fields=$true;rooted_gc_checked=$true;failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1}
