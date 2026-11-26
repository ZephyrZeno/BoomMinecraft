param([string]$Boom='target\release\boom.exe')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$boomPath=(Resolve-Path -LiteralPath $Boom).Path
$tools=Get-Content -LiteralPath (Join-Path $projectRoot '.boom\toolchain.json') -Raw|ConvertFrom-Json
$java=$tools.java;$javac=Join-Path (Split-Path -Parent $java) 'javac.exe'
$root=Join-Path $projectRoot ('.boom\numeric-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
& $javac --release 21 -encoding UTF-8 -d $classes (Join-Path $projectRoot 'java\subset\dev\boom\subset\NumericKernels.java') (Join-Path $projectRoot 'java\subset\dev\boom\subset\NumericOracle.java')
if($LASTEXITCODE -ne 0){throw 'Numeric fixture javac failed.'}
& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root
$kernel=Join-Path $classes 'dev\boom\subset\NumericKernels.class'
$methods=@('longConstant','doubleConstant','floatConstant','longMix','longShift','longNeg','longCompare','longDiv','longRem','intDiv','intRem','nestedDiv','longLoop','floatMix','doubleMix','floatDiv','doubleDiv','floatNeg','doubleNeg','floatCompare','doubleCompare','i2l','i2f','i2d','l2i','l2f','l2d','f2i','f2l','f2d','d2i','d2l','d2f','narrowByte','narrowChar','narrowShort','updateLong','updateDouble','mixedCall','manyArguments','wideSwitch')
$manifests=@{}
$compileArgs=@('compile-managed-class','--class-file',$kernel,'--output',$root,'--jobs','8','--assemble')
foreach($method in $methods){$compileArgs+=@('--method',$method)}
$text=& $boomPath @compileArgs
if($LASTEXITCODE -ne 0){throw 'Numeric class compilation failed.'}
foreach($manifest in @($text|ConvertFrom-Json)){$manifests[$manifest.method]=$manifest}
$cases=[Collections.Generic.List[object]]::new()
function Add-Case([string]$Method,[string[]]$Values){$cases.Add([pscustomobject]@{method=$Method;values=$Values})}
$ints=@('0','1','ffffffff','80000000','7fffffff','8000','ffff8000','12345678','ffffffdf','20','40')
$longs=@('0','1','ffffffffffffffff','8000000000000000','7fffffffffffffff','0123456789abcdef','fedcba9876543210','00000000ffffffff','ffffffff00000000')
$floats=@('0','80000000','3f800000','bf800000','7f800000','ff800000','7fc00000','ffc12345','7f800001','1','7fffff','800000','3f000000','4effffff','4f000000','cf000000','5effffff','5f000000','df000000','7f7fffff')
$doubles=@('0','8000000000000000','3ff0000000000000','bff0000000000000','7ff0000000000000','fff0000000000000','7ff8000000000000','fff8123456789abc','7ff0000000000001','1','000fffffffffffff','0010000000000000','3fe0000000000000','41dfffffffc00000','41e0000000000000','c1e0000000000000','43dfffffffffffff','43e0000000000000','c3e0000000000000','7fefffffffffffff')
foreach($method in @('longConstant','doubleConstant','floatConstant')){Add-Case $method @()}
foreach($a in $longs){
    Add-Case 'longNeg' @($a);Add-Case 'updateLong' @($a)
    foreach($b in $longs){foreach($method in @('longMix','longCompare','longDiv','longRem','nestedDiv')){Add-Case $method @($a,$b)}}
    foreach($b in $ints){Add-Case 'longShift' @($a,$b);Add-Case 'wideSwitch' @($b,$a)}
    foreach($steps in @('0','1','2','11','63')){Add-Case 'longLoop' @($a,$steps)}
    foreach($method in @('l2i','l2f','l2d')){Add-Case $method @($a)}
}
foreach($a in $ints){
    foreach($b in $ints){Add-Case 'intDiv' @($a,$b);Add-Case 'intRem' @($a,$b)}
    foreach($method in @('i2l','i2f','i2d','narrowByte','narrowChar','narrowShort')){Add-Case $method @($a)}
}
foreach($a in $floats){
    foreach($b in $floats){Add-Case 'floatMix' @($a,$b,'3f800001');Add-Case 'floatDiv' @($a,$b);Add-Case 'floatCompare' @($a,$b)}
    foreach($method in @('f2i','f2l','f2d','floatNeg')){Add-Case $method @($a)}
}
foreach($a in $doubles){
    foreach($b in $doubles){Add-Case 'doubleMix' @($a,$b,'3ff0000000000001');Add-Case 'doubleDiv' @($a,$b);Add-Case 'doubleCompare' @($a,$b)}
    foreach($method in @('d2i','d2l','d2f','doubleNeg','updateDouble')){Add-Case $method @($a)}
}
for($n=0;$n -lt 100;$n++){
    $argsA=@($ints[$n%$ints.Count],$longs[$n%$longs.Count],$floats[$n%$floats.Count],$doubles[$n%$doubles.Count])
    $argsB=@($ints[($n+3)%$ints.Count],$longs[($n+5)%$longs.Count],$floats[($n+7)%$floats.Count],$doubles[($n+9)%$doubles.Count])
    Add-Case 'mixedCall' $argsA;Add-Case 'manyArguments' @($argsA+$argsB)
}
$oracleInfo=[Diagnostics.ProcessStartInfo]::new();$oracleInfo.FileName=$java;$oracleInfo.UseShellExecute=$false;$oracleInfo.CreateNoWindow=$true
$oracleInfo.RedirectStandardInput=$true;$oracleInfo.RedirectStandardOutput=$true;$oracleInfo.RedirectStandardError=$true
foreach($argument in @('-cp',$classes,'dev.boom.subset.NumericOracle')){$oracleInfo.ArgumentList.Add($argument)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$oracleInfo.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$oracleInfo
try{
    if(-not $oracle.Start()){throw 'Cannot start numeric JVM oracle.'}
    $stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    foreach($case in $cases){$oracle.StandardInput.WriteLine((@($case.method)+@($case.values)-join ' ').TrimEnd())}
    $oracle.StandardInput.Close()
    if(-not $oracle.WaitForExit(30000)){$oracle.Kill($true);$oracle.WaitForExit();throw 'Numeric JVM oracle timed out.'}
    if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Oracle result count mismatch.'}
Add-Type -Path (Join-Path $projectRoot 'tests\host\NumericProbe.cs')
$failures=[Collections.Generic.List[object]]::new()
foreach($method in $methods){
    $indices=@(for($i=0;$i -lt $cases.Count;$i++){if($cases[$i].method -eq $method){$i}})
    [string[]]$inputs=@($indices|ForEach-Object{$cases[$_].values -join ' '})
    $manifest=$manifests[$method]
    if((Get-FileHash -LiteralPath $manifest.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.dll_digest.sha256){throw 'DLL identity mismatch.'}
    $actual=[BoomNumericProbe]::Run($manifest.dll,(Join-Path $root 'fpstate.dll'),$inputs,[char]$manifest.descriptor[-1])
    for($n=0;$n -lt $indices.Count;$n++){
        $i=$indices[$n];if($actual[$n] -ne $expected[$i]){$failures.Add([pscustomobject]@{case=$cases[$i];expected=$expected[$i];actual=$actual[$n]})}
    }
}
$rejections=0
foreach($method in @('unsupportedRemainder','unsupportedCatch','unsupportedReference')){
    & $boomPath compile-managed --class-file $kernel --method $method --output (Join-Path $root ('reject-'+$method)) 2>&1|Out-Null
    if($LASTEXITCODE -eq 0){throw "Unsupported managed feature accepted: $method"};$rejections++
}
$report=[ordered]@{backend='boom-numeric-v1-masm-x64';compiled_methods=$methods.Count;differential_cases=$cases.Count;native_executions=$cases.Count*2;caller_fp_states=@('nearest-gradual','truncate-FTZ-DAZ');caller_fp_state_restored=$true;rejected_features=$rejections;failures=@($failures.ToArray());passed=$failures.Count -eq 0;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 8
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
if(-not $report.passed){exit 1};exit 0
