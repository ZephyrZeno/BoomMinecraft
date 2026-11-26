param([string]$Boom='target\release\boom.exe')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$boomPath=(Resolve-Path -LiteralPath $Boom).Path
$tools=Get-Content -LiteralPath (Join-Path $projectRoot '.boom\toolchain.json') -Raw|ConvertFrom-Json
$root=Join-Path $projectRoot ('.boom\object-program-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$sources=@(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'java\subset\dev\boom\linkobjects') -Filter '*.java' -File|ForEach-Object FullName)
& (Join-Path (Split-Path -Parent $tools.java) 'javac.exe') --release 21 -proc:none -d $classes @sources (Join-Path $projectRoot 'java\subset\dev\boom\subset\ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Object program javac failed.'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
$classFiles=@(Get-ChildItem -LiteralPath (Join-Path $classes 'dev\boom\linkobjects') -Filter '*.class' -File|ForEach-Object FullName)
$methods=@('pair','wide','decimal','graph','arrays','nullField','nullStore','nullCall','nullElement','nullArray','nullArrayStore','lazyArray','lazyObject','staticGraph','cycleIdentity','constructorFailure')
$manifests=@{};$programs=@{};$baseArgs=@('compile-program','--entry-class','dev/boom/linkobjects/ObjectEntry','--assemble')
foreach($file in $classFiles){$baseArgs+=@('--class-file',$file)}
foreach($method in $methods){
    $text=& $boomPath @baseArgs --method $method --output (Join-Path $root $method)
    if($LASTEXITCODE -ne 0){throw "Object program compilation failed: $method"}
    $program=$text|ConvertFrom-Json;$programs[$method]=$program;$manifests[$method]=$program.compilation
    if($program.schema -ne 3 -or -not $program.compilation.requires_heap){throw 'Unexpected object program manifest.'}
}
$cases=[Collections.Generic.List[object]]::new()
function AddCase([string]$method,[string[]]$values){$cases.Add([pscustomobject]@{method=$method;values=$values})}
foreach($a in @('0','1','ffffffff','80000000','7fffffff','ff','ffff','12345678')){
    foreach($method in @('wide','decimal','nullField','nullStore','nullCall','nullArray','nullArrayStore','lazyArray','lazyObject','staticGraph','cycleIdentity','constructorFailure')){
        if($method -eq 'lazyArray' -and $a -in @('7fffffff','12345678','ffff')){continue}
        AddCase $method @($a)
    }
    foreach($b in @('0','1','ffffffff','80000000','7fffffff','ff')){AddCase 'pair' @($a,$b)}
}
foreach($count in @(-1,0,1,2,7,17)){
    foreach($value in @(0,1,-1,255,65535)){AddCase 'graph' @(([uint32]([int64]$value -band 4294967295)).ToString('x'),([uint32]([int64]$count -band 4294967295)).ToString('x'))}
    foreach($index in @(-1,0,1,($count-1),$count)){foreach($method in @('arrays','nullElement')){AddCase $method @(([uint32]([int64]$count -band 4294967295)).ToString('x'),([uint32]([int64]$index -band 4294967295)).ToString('x'))}}
}
# Each entry gets a fresh reference process, matching each fresh native module.
# This keeps class initialization state isolated between lazyArray and lazyObject.
$expected=@{}
foreach($method in $methods){
    $lines=@($cases|Where-Object method -eq $method|ForEach-Object{(@('dev.boom.linkobjects.ObjectEntry',$method,$manifests[$method].descriptor)+@($_.values)) -join ' '})
    $info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$tools.java;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
    foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
    $oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
    try{
        if(-not $oracle.Start()){throw 'Object program JVM reference failed to start.'}
        $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
        if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Object program reference input stalled.'}
        $oracle.StandardInput.Close();if(-not $oracle.WaitForExit(30000)){throw 'Object program reference timed out.'}
        if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
        $expected[$method]=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
    }finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
}
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
Add-Type -Path (Join-Path $projectRoot 'tests\host\ObjectProgramProbe.cs')
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $selected=@($cases|Where-Object method -eq $method);[string[]]$values=@($selected|ForEach-Object{$_.values -join ' '});$manifest=$manifests[$method]
    if((Get-FileHash -LiteralPath $manifest.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.dll_digest.sha256){throw 'Object program DLL identity mismatch.'}
    $actual=[BoomNumericProbe]::Run($manifest.dll,(Join-Path $root 'fpstate.dll'),$values,[char]$manifest.descriptor[-1],$true)
    if($expected[$method].Count -ne $selected.Count){throw 'Object reference case count mismatch.'}
    for($i=0;$i -lt $selected.Count;$i++){if($actual[$i] -ne $expected[$method][$i]){$failures.Add([pscustomobject]@{case=$selected[$i];expected=$expected[$method][$i];actual=$actual[$i]})}}
}
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
$static=$programs['staticGraph'];$node=@($static.object_layouts|Where-Object class_name -eq 'dev/boom/linkobjects/Node')[0];$box=@($static.object_layouts|Where-Object class_name -eq 'dev/boom/linkobjects/Box')[0]
function FieldOffset($layout,[string]$name){$matches=@($layout.layout.fields|Where-Object name -eq $name);if($matches.Count -ne 1){throw "Missing layout field $name"};return [int]$matches[0].offset}
[BoomObjectProgramProbe]::ColdGraph($static.compilation.dll,(Join-Path $root 'boom-runtime.dll'),$node.class_id,$box.class_id,(FieldOffset $node 'next'),(FieldOffset $node 'box'),(FieldOffset $node 'children'),(FieldOffset $node 'numbers'),(FieldOffset $box 'owner'),(FieldOffset $box 'value'))
$text=& $boomPath @baseArgs --method readNode --output (Join-Path $root 'readNode');if($LASTEXITCODE -ne 0){throw 'Receiver check module compilation failed.'};$receiver=$text|ConvertFrom-Json
$node=@($receiver.object_layouts|Where-Object class_name -eq 'dev/boom/linkobjects/Node')[0];$box=@($receiver.object_layouts|Where-Object class_name -eq 'dev/boom/linkobjects/Box')[0]
[BoomObjectProgramProbe]::ReceiverChecks($receiver.compilation.dll,(Join-Path $root 'boom-runtime.dll'),$node.class_id,$box.class_id,$receiver.entry_id)
$report=[ordered]@{backend='boom-object-program-v3-masm-x64';runtime_language='assembly';compiled_entries=$methods.Count+1;differential_cases=$cases.Count;native_executions=$cases.Count*2;cold_object_publication_records=4099;cross_class_objects=$true;constructors_and_fields=$true;named_reference_arrays=$true;static_object_graph_gc=$true;detached_cycle_reclaimed=$true;wrong_class_receiver_rejected=$true;reference_array_does_not_initialize_component=$true;failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1}
