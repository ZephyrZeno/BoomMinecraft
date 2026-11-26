param([string]$Boom='target\release\boom.exe')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$boomPath=(Resolve-Path -LiteralPath $Boom).Path
$tools=Get-Content -LiteralPath (Join-Path $projectRoot '.boom\toolchain.json') -Raw|ConvertFrom-Json
$java=$tools.java;$javac=Join-Path (Split-Path -Parent $java) 'javac.exe'
$root=Join-Path $projectRoot ('.boom\program-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$sources=@(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'java\subset\dev\boom\link') -Filter '*.java' -File|ForEach-Object FullName)
& $javac --release 21 -proc:none -encoding UTF-8 -d $classes @sources (Join-Path $projectRoot 'java\subset\dev\boom\subset\ClassNumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Linked fixtures javac failed.'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
$classFiles=@(Get-ChildItem -LiteralPath (Join-Path $classes 'dev\boom\link') -Filter '*.class' -File|Sort-Object Name|ForEach-Object FullName)
$methods=@('intRoot','longRoot','floatRoot','doubleRoot','divide','arrayRoot','arrayAlias','arrayFault','floatArray','overloadInt','overloadLong','initialized','objectReference')
$manifests=@{};$programs=@{}
$baseArgs=@('compile-program','--entry-class','dev/boom/link/LinkEntry','--assemble')
foreach($file in $classFiles){$baseArgs+=@('--class-file',$file)}
foreach($method in $methods){
    $name=$method;$extra=@()
    if($method -eq 'overloadInt'){$name='overload';$extra=@('--descriptor','(I)I')}
    if($method -eq 'overloadLong'){$name='overload';$extra=@('--descriptor','(J)J')}
    $text=& $boomPath @baseArgs --method $name --output (Join-Path $root $method) @extra
    if($LASTEXITCODE -ne 0){throw "Program compilation failed: $method"}
    $program=$text|ConvertFrom-Json;$programs[$method]=$program;$manifests[$method]=$program.compilation
    if(@($program.symbols.class_name|Select-Object -Unique).Count -lt 2){throw 'Cross-class method was not linked.'}
}
$cases=[Collections.Generic.List[object]]::new()
function Add-Case([string]$Method,[string[]]$Values){$cases.Add([pscustomobject]@{method=$Method;values=$Values})}
Add-Case 'objectReference' @()
$ints=@('0','1','ffffffff','80000000','7fffffff','12345678','8000','ffff8000')
$longs=@('0','1','ffffffffffffffff','8000000000000000','7fffffffffffffff','123456789abcdef')
$floats=@('0','80000000','3f800000','bf800000','7f800000','ff800000','7fc00000','7f800001','1','7fffff','800000','7f7fffff')
$doubles=@('0','8000000000000000','3ff0000000000000','bff0000000000000','7ff0000000000000','fff0000000000000','7ff8000000000000','7ff0000000000001','1','fffffffffffff','10000000000000','7fefffffffffffff')
foreach($a in $ints){foreach($b in $ints){foreach($method in @('intRoot','divide')){Add-Case $method @($a,$b)}};Add-Case 'overloadInt' @($a);Add-Case 'initialized' @($a)}
foreach($a in $longs){foreach($n in @(0,1,2,7,32,64)){Add-Case 'longRoot' @($a,([int]$n).ToString('x'))};Add-Case 'overloadLong' @($a)}
foreach($a in $floats){foreach($b in $floats){Add-Case 'floatRoot' @($a,$b,'3f800001')}}
foreach($a in $doubles){foreach($b in $doubles){Add-Case 'doubleRoot' @($a,$b)}}
foreach($n in @(-3,-1,0,1,2,7,32,64)){
    $nBits=([BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$n),0)).ToString('x')
    foreach($seed in $ints){foreach($method in @('arrayRoot','arrayAlias')){Add-Case $method @($nBits,$seed)}}
    foreach($seed in $floats){Add-Case 'floatArray' @($nBits,$seed)}
    foreach($index in @(-1,0,1,($n-1),$n,[int]::MinValue,[int]::MaxValue)){$indexBits=([BitConverter]::ToUInt32([BitConverter]::GetBytes([int]$index),0)).ToString('x');Add-Case 'arrayFault' @($nBits,$indexBits)}
}
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$java;$info.UseShellExecute=$false;$info.CreateNoWindow=$true
$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',$classes,'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Cannot start array JVM oracle.'}
    $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    $lines=@($cases|ForEach-Object{(@('dev.boom.link.LinkEntry',$manifests[$_.method].method,$manifests[$_.method].descriptor)+@($_.values)-join ' ').TrimEnd()})
    $write=$oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n")
    if(-not $write.Wait(15000)){$oracle.Kill($true);$oracle.WaitForExit();throw 'Program oracle input stalled.'}
    $oracle.StandardInput.Close()
    if(-not $oracle.WaitForExit(30000)){$oracle.Kill($true);$oracle.WaitForExit();throw 'Program JVM oracle timed out.'}
    if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Program oracle count mismatch.'}
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$values=@($indices|ForEach-Object{$cases[$_].values -join ' '});$manifest=$manifests[$method]
    if((Get-FileHash -LiteralPath $manifest.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.dll_digest.sha256){throw 'Program DLL hash mismatch.'}
    $actual=[BoomNumericProbe]::Run($manifest.dll,(Join-Path $root 'fpstate.dll'),$values,[char]$manifest.descriptor[-1],[bool]$manifest.requires_heap)
    for($n=0;$n -lt $indices.Count;$n++){$i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add([pscustomobject]@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}}
}
$divideSymbol=@($programs['divide'].symbols|Where-Object {$_.class_name -eq 'dev/boom/link/LinkInts' -and $_.method -eq 'divide'})
[BoomNumericProbe]::CheckExceptionOrigin($manifests['divide'].dll,[ulong[]]@(1,0),1,[uint32]$divideSymbol[0].id,2)
# Reorder inputs: symbol IDs and assembly must not depend on command-line order.
$reverse=@($classFiles);[array]::Reverse($reverse)
$orderedArgs=@('compile-program','--entry-class','dev/boom/link/LinkEntry','--method','intRoot','--output',(Join-Path $root 'reordered'))
foreach($file in $reverse){$orderedArgs+=@('--class-file',$file)}
$text=& $boomPath @orderedArgs;if($LASTEXITCODE -ne 0){throw 'Reordered linking failed.'}
$reordered=$text|ConvertFrom-Json
if($reordered.compilation.assembly_digest.sha256 -ne $manifests['intRoot'].assembly_digest.sha256){throw 'Input order changed assembly.'}
$rejections=0
$bad=@('compile-program','--entry-class','dev/boom/link/LinkEntry','--method','longRoot','--output',(Join-Path $root 'missing'))
foreach($file in $classFiles|Where-Object { [IO.Path]::GetFileName($_) -ne 'LinkNumbers.class' }){$bad+=@('--class-file',$file)}
& $boomPath @bad 2>&1|Out-Null;if($LASTEXITCODE -eq 0){throw 'Missing dependency accepted.'};$rejections++
& $boomPath @baseArgs --class-file $classFiles[0] --method intRoot --output (Join-Path $root 'duplicate') 2>&1|Out-Null
if($LASTEXITCODE -eq 0){throw 'Duplicate definition accepted.'};$rejections++
$report=[ordered]@{backend='boom-object-program-v3-masm-x64';runtime_language='assembly';compiled_entries=$methods.Count;differential_cases=$cases.Count;native_executions=$cases.Count*2;cross_class_primitive_arrays=$true;void_calls=$true;overload_resolution=$true;exception_origin_checked=$true;deterministic_input_order=$true;rejected_features=$rejections;failures=@($failures.ToArray());passed=$failures.Count -eq 0;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1};exit 0
