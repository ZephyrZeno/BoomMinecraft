param([string]$Launcher='dist\BoomLauncher.exe',[string]$Boom='dist\boom.exe')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$info=[Diagnostics.ProcessStartInfo]::new()
$info.FileName=(Resolve-Path -LiteralPath $Launcher).Path
$info.UseShellExecute=$false; $info.CreateNoWindow=$true
$info.RedirectStandardOutput=$true; $info.RedirectStandardError=$true
foreach($argument in @('--self-test','--workspace',$projectRoot)) { $info.ArgumentList.Add($argument) }
$process=[Diagnostics.Process]::new();$process.StartInfo=$info
try {
    if(-not $process.Start()) { throw 'Cannot start headless launcher test.' }
    $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
    if(-not $process.WaitForExit(30000)) { $process.Kill($true);$process.WaitForExit();throw 'Headless launcher test timed out.' }
    if($process.ExitCode -ne 0) { throw $stderr.GetAwaiter().GetResult() }
    $stdout.GetAwaiter().GetResult() | Write-Output
} finally { $process.Dispose() }
$report=Get-Content -LiteralPath (Join-Path $projectRoot '.boom\launcher-selftest\result.json') -Raw | ConvertFrom-Json
if(-not $report.passed -or $report.ui_automation_used -or $report.compiler_buttons) { throw 'Invalid launcher self-test result.' }
$target=Join-Path $projectRoot ('.boom\launcher-selftest\not-started-'+[guid]::NewGuid().ToString('N'))
& $Boom play --game-dir $target --memory-mib 4096 2>&1 | ForEach-Object { Write-Output "$_" }
if($LASTEXITCODE -ne 1) { throw 'Expected incomplete game runtime to reject player launch.' }
if(Test-Path -LiteralPath $target) { throw 'Failed preflight created game data.' }
Write-Output 'Headless launcher and player preflight checks passed. Complete game launch remains unavailable.'
exit 0
