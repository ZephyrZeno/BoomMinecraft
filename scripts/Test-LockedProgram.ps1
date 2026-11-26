param([string]$Lock='.boom\locks\client.json',[string]$Boom='target\release\boom.exe')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
& $Boom verify --lock $Lock|Out-Null
if($LASTEXITCODE -ne 0){throw 'Locked client inputs failed verification.'}
$inputs=Get-Content -LiteralPath $Lock -Raw|ConvertFrom-Json
$root=Join-Path $projectRoot ('.boom\locked-program-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$paths=@($inputs.classpath|ForEach-Object{$id=$_;($inputs.files|Where-Object id -eq $id).path})
$javac=Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe'
& $javac --release 21 -proc:none -cp ($paths -join ';') -d $classes (Join-Path $projectRoot 'java\subset\dev\boom\subset\ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Locked program oracle javac failed.'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
$destination=Join-Path $root 'color'
$text=& $Boom compile-locked-program --lock $Lock --entry-class 'axy$b' --method a --descriptor '(II)I' --output $destination --assemble
if($LASTEXITCODE -ne 0){throw 'Locked call closure compilation failed.'}
$locked=$text|ConvertFrom-Json;$program=$locked.program;$manifest=$program.compilation
if($locked.input_fingerprint -ne $inputs.fingerprint -or $program.symbols.Count -ne 6 -or $locked.origins.Count -ne 1){throw 'Unexpected locked color call closure.'}
foreach($source in $program.sources){
    $origin=@($locked.origins|Where-Object { $_.binary_name -eq $source.class_name.Replace('/','.') })
    if($origin.Count -ne 1 -or $source.digest.sha256 -ne $origin[0].sha256){throw 'Program source provenance mismatch.'}
}
if((Get-FileHash -LiteralPath $manifest.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.dll_digest.sha256){throw 'Program DLL identity mismatch.'}
$bits=@('0','1','ffffffff','80000000','7fffffff','12345678','ffff0000','7f0000ff','ff000000','00ffffff','80808080','ff00ff00')
$cases=[Collections.Generic.List[object]]::new()
foreach($a in $bits){foreach($b in $bits){$cases.Add([pscustomobject]@{values=@($a,$b)})}}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',((@($classes)+$paths) -join ';'),'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Cannot start locked program JVM oracle.'}
    $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    $lines=@($cases|ForEach-Object{(@('axy$b','a','(II)I')+@($_.values)) -join ' '})
    if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Locked program oracle input stalled.'}
    $oracle.StandardInput.Close()
    if(-not $oracle.WaitForExit(30000)){throw 'Locked program oracle timed out.'}
    if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Locked program oracle count mismatch.'}
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
$failures=[Collections.Generic.List[object]]::new()
[string[]]$values=@($cases|ForEach-Object{$_.values -join ' '})
$actual=[BoomNumericProbe]::Run($manifest.dll,(Join-Path $root 'fpstate.dll'),$values,'I')
for($i=0;$i -lt $cases.Count;$i++){if($actual[$i] -ne $expected[$i]){$failures.Add([pscustomobject]@{case=$cases[$i];expected=$expected[$i];actual=$actual[$i]})}}
# This original method reaches an unsupported initializer dependency. Never skip it.
$blocked=& $Boom compile-locked-program --lock $Lock --entry-class 'axy$b' --method a --descriptor '(FII)I' --output (Join-Path $root 'unsupported-color') --assemble 2>&1
if($LASTEXITCODE -eq 0){throw 'Unsupported original initializer dependency was accepted.'}
$blockedText=($blocked|ForEach-Object ToString) -join "`n"
[IO.File]::WriteAllText((Join-Path $root 'unsupported-color.txt'),$blockedText,[Text.UTF8Encoding]::new($false))
$report=[ordered]@{backend='boom-object-program-v3-masm-x64';runtime_language='assembly';input_fingerprint=$inputs.fingerprint;class='axy$b';entry_descriptor='(II)I';linked_methods=$program.symbols.Count;automatic_closure=$true;original_class_unchanged=$true;differential_cases=$cases.Count;native_executions=$cases.Count*2;unsupported_linked_dependency_rejected=$true;blocked_reason=$blockedText;failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1}
