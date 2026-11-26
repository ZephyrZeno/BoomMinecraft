param(
    [string]$Binary = '.boom\native\server-startup\minecraft-server.exe',
    [string]$OutputDirectory = '.boom\reports\native-startup'
)

$ErrorActionPreference = 'Stop'
$binaryPath = (Resolve-Path -LiteralPath $Binary).Path
$reportRoot = [System.IO.Path]::GetFullPath($OutputDirectory)
[System.IO.Directory]::CreateDirectory($reportRoot) | Out-Null
$results = @()

foreach ($case in @(@{ Name = 'help'; Argument = '--help' }, @{ Name = 'init-settings'; Argument = '--initSettings' })) {
    $caseDirectory = Join-Path $reportRoot $case.Name
    [System.IO.Directory]::CreateDirectory($caseDirectory) | Out-Null
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $binaryPath
    $startInfo.WorkingDirectory = $caseDirectory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.ArgumentList.Add('-Xmx2g')
    $startInfo.ArgumentList.Add($case.Argument)
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    $started = $false
    try {
        if (-not $process.Start()) { throw 'Cannot start native executable.' }
        $started = $true
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $finished = $process.WaitForExit(45000)
        if (-not $finished) {
            $process.Kill($true)
            $process.WaitForExit()
        }
        $log = $stdoutTask.GetAwaiter().GetResult() + "`n" + $stderrTask.GetAwaiter().GetResult()
        [System.IO.File]::WriteAllText((Join-Path $caseDirectory 'startup.log'), $log, [System.Text.UTF8Encoding]::new($false))
        $runtimeError = $log -match 'UnsupportedFeatureError|Exception in thread|ERROR StatusLogger|could not find a logging implementation'
        $expectedOutput = if ($case.Name -eq 'help') { $log -match '--initSettings' } else { Test-Path -LiteralPath (Join-Path $caseDirectory 'server.properties') }
        $eulaPath = Join-Path $caseDirectory 'eula.txt'
        $eulaAccepted = (Test-Path -LiteralPath $eulaPath) -and [bool]((Get-Content -LiteralPath $eulaPath) -match '^eula=true$')
        $results += [ordered]@{
            case = $case.Name
            exit_code = $process.ExitCode
            timed_out = -not $finished
            runtime_error_detected = $runtimeError
            expected_output = $expectedOutput
            eula_accepted = $eulaAccepted
            passed = $finished -and $process.ExitCode -eq 0 -and -not $runtimeError -and $expectedOutput -and -not $eulaAccepted
        }
    } finally {
        if ($started -and -not $process.HasExited) { $process.Kill($true); $process.WaitForExit() }
        $process.Dispose()
    }
}

$report = [ordered]@{
    binary = $binaryPath
    scope = 'help and settings initialization only'
    full_game_validated = $false
    cases = $results
    passed = @($results | Where-Object { -not $_.passed }).Count -eq 0
}
$reportJson = $report | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText((Join-Path $reportRoot 'startup-result.json'), $reportJson, [System.Text.UTF8Encoding]::new($false))
Write-Output $reportJson
if (-not $report.passed) { exit 1 }
