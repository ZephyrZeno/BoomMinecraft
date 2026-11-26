param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\client.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content -LiteralPath (Join-Path $projectRoot '.boom\latest-jdk-base.txt') -Raw).Trim()) 'jdk-base.json'}
$boomPath=(Resolve-Path -LiteralPath $Boom).Path
$root=Join-Path $projectRoot ('.boom\inheritance-program-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$tools=Get-Content -LiteralPath (Join-Path $projectRoot '.boom\toolchain.json') -Raw|ConvertFrom-Json
$sources=@(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'java\subset\dev\boom\inheritance') -Filter '*.java' -File -Recurse|ForEach-Object FullName)
& (Join-Path (Split-Path -Parent $tools.java) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes @sources (Join-Path $projectRoot 'java\subset\dev\boom\subset\ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Interface fixture javac failed.'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
$baseArgs=@('compile-program','--entry-class','dev/boom/inheritance/InheritanceEntry','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--assemble')
foreach($file in Get-ChildItem -LiteralPath (Join-Path $classes 'dev\boom\inheritance') -Filter '*.class' -File -Recurse){$baseArgs+=@('--class-file',$file.FullName)}
$methods=@('fields','hidden','constructed','wide','decimal','casts','initialization','inheritedStatic','inheritedDefault','special','array','arrayFault','nullArrayStore','interfaceArray','retained','constructorFailure');$programs=@{}
foreach($method in $methods){
    $text=& $boomPath @baseArgs --method $method --output (Join-Path $root $method)
    if($LASTEXITCODE -ne 0){throw "Inheritance program compilation failed: $method"}
    $program=$text|ConvertFrom-Json;$programs[$method]=$program
    if($program.schema -ne 10 -or $program.full_game_ready){throw 'Unexpected compact inheritance manifest.'}
    Write-Output "Compiled inheritance entry: $method"
}
$cases=[Collections.Generic.List[object]]::new()
function Bits([int]$value){return ([BitConverter]::ToUInt32([BitConverter]::GetBytes($value),0)).ToString('x')}
foreach($kind in @(-1,0,1,2,3,7,[int]::MinValue,[int]::MaxValue)){
    foreach($n in @(-1,0,1,7,32768,[int]::MinValue,[int]::MaxValue)){
        foreach($method in @('fields','casts','special')){$cases.Add([pscustomobject]@{method=$method;values=@((Bits $kind),(Bits $n))})}
        foreach($extra in @('0','1','ffffffffffffffff','8000000000000000','7fffffffffffffff')){$cases.Add([pscustomobject]@{method='wide';values=@((Bits $kind),(Bits $n),$extra)})}
        foreach($extra in @('0','8000000000000000','3ff8000000000000','c004000000000000','7ff8000000000000','7ff0000000000000')){$cases.Add([pscustomobject]@{method='decimal';values=@((Bits $kind),(Bits $n),$extra)})}
    }
}
foreach($n in @(-1,0,1,7,32768,[int]::MinValue,[int]::MaxValue)){
    foreach($method in @('hidden','constructed','initialization','inheritedStatic','inheritedDefault','array','interfaceArray','retained','constructorFailure')){$cases.Add([pscustomobject]@{method=$method;values=@((Bits $n))})}
}
foreach($kind in @(0,1,2)){foreach($index in @(-1,0,1,2)){foreach($n in @(0,7)){$cases.Add([pscustomobject]@{method='arrayFault';values=@((Bits $kind),(Bits $n),(Bits $index))})}}}
foreach($index in @(-1,0,1,2)){$cases.Add([pscustomobject]@{method='nullArrayStore';values=@((Bits $index))})}
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $manifest=$programs[$method].compilation
    $selected=@($cases|Where-Object method -eq $method)
    $lines=@($selected|ForEach-Object{(@('dev.boom.inheritance.InheritanceEntry',$method,$manifest.descriptor)+@($_.values)) -join ' '})
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$tools.java;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
    try{
        if(-not $oracle.Start()){throw 'Interface JVM reference failed.'}
        $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
        if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Interface JVM input stalled.'}
        $oracle.StandardInput.Close();if(-not $oracle.WaitForExit(30000)){throw 'Interface JVM reference timed out.'}
        if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
        $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
    }finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
    if($expected.Count -ne $selected.Count){throw 'Interface reference case count mismatch.'}
    if((Get-FileHash -LiteralPath $manifest.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.dll_digest.sha256){throw 'Interface module hash mismatch.'}
    [string[]]$values=@($selected|ForEach-Object{$_.values -join ' '})
    $actual=[BoomNumericProbe]::Run($manifest.dll,(Join-Path $root 'fpstate.dll'),$values,[char]$manifest.descriptor[-1],$true)
    for($i=0;$i -lt $selected.Count;$i++){if($actual[$i] -ne $expected[$i]){$failures.Add([pscustomobject]@{case=$selected[$i];expected=$expected[$i];actual=$actual[$i]})}}
}
$layoutProgram=$programs['fields']
foreach($name in @('Base','Child','Grand')){
    $layout=@($layoutProgram.object_layouts|Where-Object class_name -eq "dev/boom/inheritance/$name")[0].layout
    $refs=if($name -eq 'Base'){1}elseif($name -eq 'Child'){2}else{3}
    if($layout.reference_prefix_fields -ne $refs){throw "Inherited reference prefix mismatch: $name"}
    $slot=@($layout.fields|Where-Object{$_.name -eq 'value' -and $_.declaring_class -eq 'dev/boom/inheritance/Base'})
    if($layout.abi -ne 2 -or $slot.Count -ne 1 -or $slot[0].offset -ne $refs*8+16 -or $slot[0].storage_bytes -ne 4){throw "Inherited compact scalar offset mismatch: $name"}
}
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
Add-Type -Path (Join-Path $projectRoot 'tests\host\InheritanceProbe.cs')
[BoomInheritanceProbe]::Cold($programs['retained'].compilation.dll,(Join-Path $root 'boom-runtime.dll'),58)
$report=[ordered]@{backend='boom-compact-program-v10-masm-x64';runtime_language='assembly';object_layout_abi=2;compiled_entries=$methods.Count;differential_cases=$cases.Count;native_executions=$cases.Count*2;inherited_reference_prefix=$true;hidden_and_private_fields=$true;superclass_constructors=$true;constructor_virtual_dispatch=$true;constructor_delegation=$true;special_super_and_default_calls=$true;covariant_reference_arrays=$true;array_exception_precedence=$true;inherited_static_graph_gc=$true;cold_multicore_records=4099;workers=8;inherited_static_owner=$true;default_interface_initialization_order=$true;failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1}
