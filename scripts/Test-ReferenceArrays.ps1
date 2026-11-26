param([string]$Boom='target\release\boom.exe')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$boomPath=(Resolve-Path -LiteralPath $Boom).Path
$tools=Get-Content -LiteralPath (Join-Path $projectRoot '.boom\toolchain.json') -Raw|ConvertFrom-Json
$java=$tools.java;$javac=Join-Path (Split-Path -Parent $java) 'javac.exe'
$root=Join-Path $projectRoot ('.boom\reference-array-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
& $javac --release 21 -encoding UTF-8 -d $classes (Join-Path $projectRoot 'java\subset\dev\boom\subset\ReferenceArrayKernels.java') (Join-Path $projectRoot 'java\subset\dev\boom\subset\ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Object fixture javac failed.'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
$kernel=Join-Path $classes 'dev\boom\subset\ReferenceArrayKernels.class'
$methods=@('sumArray','nullElements','replaceArray','arrayField','cyclicArray','nullArray','identity')
$manifests=@{}
$compileArgs=@('compile-managed-class','--class-file',$kernel,'--output',$root,'--jobs','8','--assemble')
foreach($method in $methods){$compileArgs+=@('--method',$method)}
$text=& $boomPath @compileArgs
if($LASTEXITCODE -ne 0){throw 'Object class compilation failed.'}
foreach($manifest in @($text|ConvertFrom-Json)){$manifests[$manifest.method]=$manifest;if(-not $manifest.requires_heap){throw 'Object bytecode did not declare its assembly runtime dependency.'}}
$cases=[Collections.Generic.List[object]]::new()
function Add-Case([string]$Method,[string[]]$Values){$cases.Add([pscustomobject]@{method=$Method;values=$Values})}
$ints=@('0','1','ffffffff','80000000','7fffffff','12345678','8000','ffff8000')
$longs=@('0','1','ffffffffffffffff','8000000000000000','7fffffffffffffff','123456789abcdef')
$floats=@('0','80000000','3f800000','bf800000','7f800000','ff800000','7fc00000','7f800001','1','7fffff','800000','7f7fffff')
$doubles=@('0','8000000000000000','3ff0000000000000','bff0000000000000','7ff0000000000000','fff0000000000000','7ff8000000000000','7ff0000000000001','1','fffffffffffff','10000000000000','7fefffffffffffff')
foreach($count in @(-3,-1,0,1,2,7,32,64)){
    $nBits=([BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$count),0)).ToString('x')
    foreach($seed in $ints){foreach($method in @('sumArray','replaceArray','arrayField')){Add-Case $method @($nBits,$seed)}}
    foreach($index in @(-1,0,1,($count-1),$count,[int]::MinValue,[int]::MaxValue)){
        $indexBits=([BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$index),0)).ToString('x')
        Add-Case 'nullElements' @($nBits,$indexBits)
    }
    foreach($method in @('nullArray','identity')){Add-Case $method @($nBits)}
}
foreach($seed in $ints){Add-Case 'cyclicArray' @($seed)}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$java;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Cannot start array JVM oracle.'}
    $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    $lines=@($cases|ForEach-Object{(@('dev.boom.subset.ReferenceArrayKernels',$_.method,$manifests[$_.method].descriptor)+@($_.values)-join ' ').TrimEnd()})
    $write=$oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n")
    if(-not $write.Wait(15000)){$oracle.Kill($true);$oracle.WaitForExit();throw 'Object oracle input stalled.'}
    $oracle.StandardInput.Close()
    if(-not $oracle.WaitForExit(30000)){$oracle.Kill($true);$oracle.WaitForExit();throw 'Object JVM oracle timed out.'}
    if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Object oracle count mismatch.'}
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '});$manifest=$manifests[$method]
    if((Get-FileHash -LiteralPath $manifest.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.dll_digest.sha256){throw 'Object DLL hash mismatch.'}
    $actual=[BoomNumericProbe]::Run($manifest.dll,(Join-Path $root 'fpstate.dll'),$values,[char]$manifest.descriptor[-1],$true)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add([pscustomobject]@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
& $boomPath compile-managed --class-file $kernel --method retainedArray --output (Join-Path $root 'retainedArray') --assemble|Out-Null
if($LASTEXITCODE -ne 0){throw 'Retained graph compilation failed.'}
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
[BoomNumericProbe]::CheckRetainedArray((Join-Path $root 'retainedArray\method.dll'),(Join-Path $root 'boom-runtime.dll'))
$report=[ordered]@{backend='boom-numeric-v1-masm-x64';runtime_language='assembly';compiled_methods=$methods.Count;differential_cases=$cases.Count;native_executions=$cases.Count*2;typed_reference_arrays_sameclass_only=$true;array_store_type_check=$true;constructors=$true;reference_fields=$true;typed_reference_array_fields=$true;heap_binding=$true;post_entry_explicit_gc=$true;rooted_cycle_and_array_survival=$true;automatic_gc_during_java_execution=$false;failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1};exit 0
