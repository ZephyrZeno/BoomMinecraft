param([string]$Boom='target\release\boom.exe')

$ErrorActionPreference='Stop'
$projectRoot=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$boomPath=(Resolve-Path -LiteralPath $Boom).Path
$tools=Get-Content -LiteralPath (Join-Path $projectRoot '.boom\toolchain.json') -Raw | ConvertFrom-Json
$java=(Resolve-Path -LiteralPath $tools.java).Path
$javac=Join-Path (Split-Path -Parent $java) 'javac.exe'
$root=Join-Path $projectRoot ('.boom\compiler-tests\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes'
[System.IO.Directory]::CreateDirectory($classes) | Out-Null
$sources=@('IntKernels.java','StatefulKernel.java','IntOracle.java') | ForEach-Object { Join-Path $projectRoot ('java\subset\dev\boom\subset\'+$_) }
& $javac --release 21 -encoding UTF-8 -d $classes @sources
if ($LASTEXITCODE -ne 0) { throw 'Cannot compile Java oracle fixtures.' }
$kernel=Join-Path $classes 'dev\boom\subset\IntKernels.class'

function Invoke-Tool {
    param([string[]]$Arguments)
    $info=[System.Diagnostics.ProcessStartInfo]::new()
    $info.FileName=$boomPath
    $info.UseShellExecute=$false
    $info.CreateNoWindow=$true
    $info.RedirectStandardOutput=$true
    $info.RedirectStandardError=$true
    foreach ($argument in $Arguments) { $info.ArgumentList.Add($argument) }
    $process=[System.Diagnostics.Process]::new()
    $process.StartInfo=$info
    $started=$false
    try {
        $started=$process.Start()
        if (-not $started) { throw 'Cannot start compiler command.' }
        $stdout=$process.StandardOutput.ReadToEndAsync()
        $stderr=$process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(15000)) { $process.Kill($true); $process.WaitForExit(); throw 'Compiler or native method timed out.' }
        return [pscustomobject]@{ exit_code=$process.ExitCode; stdout=$stdout.GetAwaiter().GetResult(); stderr=$stderr.GetAwaiter().GetResult() }
    } finally {
        if ($started -and -not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
        $process.Dispose()
    }
}

$methods=@('constant','mix','signedCompare','abs','shifts','sumTo','choose','nested','bump','four','fib','denseSwitch','sparseSwitch','callChain','nestedCalls','parallelWork')
$manifests=@{}
foreach ($method in $methods) {
    $output=Join-Path $root $method
    $compiled=Invoke-Tool @('compile-asm','--class-file',$kernel,'--method',$method,'--output',$output,'--assemble')
    if ($compiled.exit_code -ne 0) { throw "Compilation failed for ${method}: $($compiled.stderr)" }
    $manifests[$method]=Join-Path $output 'compilation.json'
}

$cases=[System.Collections.Generic.List[object]]::new()
function Add-Case { param([string]$Method,[int[]]$Values); $cases.Add([pscustomobject]@{method=$Method;values=$Values}) }
$bounds=@([int]::MinValue,[int]::MaxValue,-1000,-33,-32,-1,0,1,31,32,33,1000)
Add-Case 'constant' @()
foreach ($a in $bounds) {
    Add-Case 'abs' @($a)
    Add-Case 'bump' @($a)
    foreach ($b in $bounds) {
        Add-Case 'mix' @($a,$b)
        Add-Case 'signedCompare' @($a,$b)
        Add-Case 'shifts' @($a,$b)
        Add-Case 'choose' @($a,$b,($a -bxor $b))
        Add-Case 'four' @($a,$b,$b,$a)
    }
}
foreach ($n in @(-3,0,1,2,3,7,16,30)) { Add-Case 'fib' @($n); Add-Case 'sumTo' @($n); foreach ($m in @(-1,0,1,4,9)) { Add-Case 'nested' @($n,$m) } }
foreach ($a in @($bounds)+@(-701,-2,2,30000)) {
    Add-Case 'denseSwitch' @($a)
    Add-Case 'sparseSwitch' @($a)
    Add-Case 'nestedCalls' @($a)
    Add-Case 'parallelWork' @($a,1013904223,255,257)
    foreach ($b in $bounds) { Add-Case 'callChain' @($a,$b,$b,$a) }
}
$oracleInfo=[System.Diagnostics.ProcessStartInfo]::new()
$oracleInfo.FileName=$java
$oracleInfo.UseShellExecute=$false
$oracleInfo.CreateNoWindow=$true
$oracleInfo.RedirectStandardInput=$true
$oracleInfo.RedirectStandardOutput=$true
$oracleInfo.RedirectStandardError=$true
foreach ($argument in @('-cp',$classes,'dev.boom.subset.IntOracle')) { $oracleInfo.ArgumentList.Add($argument) }
foreach ($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')) { $oracleInfo.Environment.Remove($key) | Out-Null }
$oracle=[System.Diagnostics.Process]::new()
$oracle.StartInfo=$oracleInfo
$oracleStarted=$false
try {
    $oracleStarted=$oracle.Start()
    if (-not $oracleStarted) { throw 'Cannot start JVM oracle.' }
    $oracleOut=$oracle.StandardOutput.ReadToEndAsync()
    $oracleError=$oracle.StandardError.ReadToEndAsync()
    foreach ($case in $cases) { $oracle.StandardInput.WriteLine((@($case.method)+@($case.values) -join ' ').TrimEnd()) }
    $oracle.StandardInput.Close()
    if (-not $oracle.WaitForExit(30000)) { $oracle.Kill($true); $oracle.WaitForExit(); throw 'JVM oracle timed out.' }
    if ($oracle.ExitCode -ne 0) { throw $oracleError.GetAwaiter().GetResult() }
    $expected=@($oracleOut.GetAwaiter().GetResult().Split("`n",[System.StringSplitOptions]::RemoveEmptyEntries) | ForEach-Object { [int]$_.Trim() })
} finally {
    if ($oracleStarted -and -not $oracle.HasExited) { $oracle.Kill($true); $oracle.WaitForExit() }
    $oracle.Dispose()
}
if ($expected.Count -ne $cases.Count) { throw 'JVM oracle did not return one result per case.' }
$failures=[System.Collections.Generic.List[object]]::new()
for ($index=0; $index -lt $cases.Count; $index++) {
    $case=$cases[$index]
    $arguments=@('execute-asm','--manifest',$manifests[$case.method])+@($case.values | ForEach-Object { "--arg=$_" })
    $actual=Invoke-Tool $arguments
    if ($actual.exit_code -ne 0) { $failures.Add([pscustomobject]@{case=$case;error=$actual.stderr}); break }
    $value=($actual.stdout | ConvertFrom-Json).result
    if ($value -ne $expected[$index]) { $failures.Add([pscustomobject]@{case=$case;expected=$expected[$index];actual=$value}) }
}
$rejections=0
foreach ($method in @('divide','calls','monitor','allocation','handler','recursive')) {
    $rejected=Invoke-Tool @('compile-asm','--class-file',$kernel,'--method',$method,'--output',(Join-Path $root ('reject-'+$method)))
    if ($rejected.exit_code -eq 0) { throw "Unsupported method was silently accepted: $method" }
    $rejections++
}
$rejected=Invoke-Tool @('compile-asm','--class-file',(Join-Path $classes 'dev\boom\subset\StatefulKernel.class'),'--method','read','--output',(Join-Path $root 'reject-stateful'))
if ($rejected.exit_code -eq 0) { throw 'Class initialization was silently accepted.' }
$rejections++
$report=[ordered]@{ backend='boom-i32-v2-masm-x64'; pipeline='class -> own decoder and verifier -> generated MASM -> ml64 -> link -> native DLL'; jvm_oracle=$java; compiled_methods=$methods.Count; differential_cases=$cases.Count; rejected_unsupported_methods=$rejections; failures=@($failures.ToArray()); passed=$failures.Count -eq 0; run_directory=$root }
$json=$report | ConvertTo-Json -Depth 7
[System.IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[System.Text.UTF8Encoding]::new($false))
Write-Output $json
if (-not $report.passed) { exit 1 }
