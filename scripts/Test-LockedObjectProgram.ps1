param([string]$Lock='.boom\locks\client.json',[string]$Boom='target\release\boom.exe')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$inputs=Get-Content -LiteralPath $Lock -Raw|ConvertFrom-Json
$root=Join-Path $projectRoot ('.boom\locked-object-program-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$paths=@($inputs.classpath|ForEach-Object{$id=$_;($inputs.files|Where-Object id -eq $id).path})
$sources=@('RangeProgramEntry','ClassNumericOracle','RangeObjectOracle'|ForEach-Object{Join-Path $projectRoot "java\subset\dev\boom\subset\$_.java"})
& (Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe') --release 21 -proc:none -cp ($paths -join ';') -d $classes @sources
if($LASTEXITCODE -ne 0){throw 'Locked object program reference javac failed.'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
$original='com/mojang/brigadier/context/StringRange'
$text=& $Boom compile-locked-program --lock $Lock --entry-class $original --method between --descriptor '(II)Lcom/mojang/brigadier/context/StringRange;' --output (Join-Path $root 'factory') --assemble
if($LASTEXITCODE -ne 0){throw 'Locked object factory closure compilation failed.'}
$locked=$text|ConvertFrom-Json;$factory=$locked.program
if($locked.origins.Count -ne 1 -or $factory.sources.Count -ne 1 -or $factory.sources[0].digest.sha256 -ne $locked.origins[0].sha256 -or $locked.origins[0].loader -ne 'vanilla-application'){throw 'Original factory lost its locked provenance.'}
$originalClass=$factory.sources[0].path
if((Get-FileHash -LiteralPath $originalClass -Algorithm SHA256).Hash.ToLowerInvariant() -ne $locked.origins[0].sha256){throw 'Extracted original class changed.'}
$programs=@{}
foreach($method in @('length','start')){
    $text=& $Boom compile-program --class-file $originalClass --class-file (Join-Path $classes 'dev\boom\subset\RangeProgramEntry.class') --entry-class dev/boom/subset/RangeProgramEntry --method $method --output (Join-Path $root $method) --assemble
    if($LASTEXITCODE -ne 0){throw 'Locked cross-class object invocation compilation failed.'}
    $programs[$method]=$text|ConvertFrom-Json
    if(@($programs[$method].symbols.class_name|Select-Object -Unique).Count -ne 2){throw 'Expected original class and independent caller.'}
}
$bits=@('0','1','ffffffff','80000000','7fffffff','12345678','ffff0000','7f0000ff','a','fffffff6','8001','ffff7fff')
$cases=[Collections.Generic.List[object]]::new()
foreach($start in $bits){$cases.Add([pscustomobject]@{method='start';values=@($start)});foreach($end in $bits){$cases.Add([pscustomobject]@{method='length';values=@($start,$end)})}}
function Reference([string]$main,[string[]]$lines){
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('-cp',((@($classes)+$paths) -join ';'),$main)){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
    try{
        if(-not $oracle.Start()){throw 'Locked object reference failed to start.'}
        $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
        if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Locked object reference input stalled.'}
        $oracle.StandardInput.Close();if(-not $oracle.WaitForExit(30000)){throw 'Locked object reference timed out.'}
        if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
        return @($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
    }finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
}
$lines=@($cases|ForEach-Object{(@('dev.boom.subset.RangeProgramEntry',$_.method,$programs[$_.method].compilation.descriptor)+@($_.values)) -join ' '})
$expected=@(Reference 'dev.boom.subset.ClassNumericOracle' $lines)
if($expected.Count -ne $cases.Count){throw 'Original object call reference case count mismatch.'}
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
$failures=[Collections.Generic.List[object]]::new()
foreach($method in @('length','start')){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '});$manifest=$programs[$method].compilation
    $actual=[BoomNumericProbe]::Run($manifest.dll,(Join-Path $root 'fpstate.dll'),$values,'I',$true)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add([pscustomobject]@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
$factoryCases=@($cases|Where-Object method -eq 'length');$lines=@($factoryCases|ForEach-Object{(@('between')+@($_.values)) -join ' '})
$factoryExpected=@(Reference 'dev.boom.subset.RangeObjectOracle' $lines)
$layout=@($factory.object_layouts|Where-Object class_name -eq $original)[0].layout
[int[]]$offsets=@(foreach($name in @('start','end')){($layout.fields|Where-Object name -eq $name).offset})
[string[]]$values=@($factoryCases|ForEach-Object{$_.values -join ' '})
$actual=[BoomNumericProbe]::InspectIntObject($factory.compilation.dll,(Join-Path $root 'fpstate.dll'),$values,$offsets)
for($i=0;$i -lt $factoryCases.Count;$i++){if($actual[$i] -ne $factoryExpected[$i]){$failures.Add([pscustomobject]@{factory_case=$factoryCases[$i];expected=$factoryExpected[$i];actual=$actual[$i]})}}
$report=[ordered]@{backend='boom-object-program-v3-masm-x64';runtime_language='assembly';input_fingerprint=$inputs.fingerprint;original_class=$original;original_sha256=$locked.origins[0].sha256;actual_locked_class_unchanged=$true;automatic_factory_closure=$true;linked_factory_methods=$factory.symbols.Count;cross_class_differential_cases=$cases.Count;factory_differential_cases=$factoryCases.Count;native_executions=($cases.Count+$factoryCases.Count)*2;rooted_factory_gc=$true;failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1}
