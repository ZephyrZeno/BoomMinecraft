param(
    [string]$Lock = '.boom\locks\server-graal21.json',
    [string]$Binary = '.boom\native\server-compatible\minecraft-server.exe',
    [string]$Boom = 'target\release\boom.exe',
    [switch]$AcceptEula,
    [int]$StageTimeoutSeconds = 180
)

$ErrorActionPreference = 'Stop'
if (-not $AcceptEula) {
    throw 'World tests require agreement to https://aka.ms/MinecraftEULA. Pass -AcceptEula only after accepting it. Acceptance is written only to isolated test directories.'
}
if ($StageTimeoutSeconds -lt 10 -or $StageTimeoutSeconds -gt 600) { throw 'Stage timeout must be between 10 and 600 seconds.' }
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$binaryPath = (Resolve-Path -LiteralPath $Binary).Path
$boomPath = (Resolve-Path -LiteralPath $Boom).Path
$lockPath = (Resolve-Path -LiteralPath $Lock).Path
$inputs = Get-Content -LiteralPath $lockPath -Raw | ConvertFrom-Json
if ($inputs.side -ne 'server' -or $inputs.game_version -ne '1.21.1') { throw 'A vanilla 1.21.1 server lock is required.' }
$runRoot = Join-Path $projectRoot ('.boom\runs\roundtrip\' + [guid]::NewGuid().ToString('N'))
$metadataRoot = Join-Path $projectRoot '.boom\metadata\server-world'
$temporaryRoot = Join-Path $projectRoot '.boom\tmp'
[System.IO.Directory]::CreateDirectory($runRoot) | Out-Null
[System.IO.Directory]::CreateDirectory($metadataRoot) | Out-Null
[System.IO.Directory]::CreateDirectory($temporaryRoot) | Out-Null
$toolchain = Get-Content -LiteralPath (Join-Path $projectRoot '.boom\toolchain.json') -Raw | ConvertFrom-Json
$graalHome = Split-Path -Parent (Split-Path -Parent $toolchain.native_image)
$agent = Join-Path $graalHome 'bin\native-image-agent.dll'
$stages = @()

function Invoke-WorldStage {
    param([string]$Name, [bool]$Native, [string]$CopyWorld, [string]$ExpectedBlock, [int]$ExpectedScore, [string]$WriteBlock, [int]$WriteScore)
    $directory = Join-Path $runRoot $Name
    [System.IO.Directory]::CreateDirectory($directory) | Out-Null
    if ($CopyWorld) {
        if (-not (Test-Path -LiteralPath (Join-Path $CopyWorld 'level.dat'))) { throw 'Source world was not saved.' }
        Copy-Item -LiteralPath $CopyWorld -Destination (Join-Path $directory 'world') -Recurse
    }
    [System.IO.File]::WriteAllText((Join-Path $directory 'eula.txt'), "eula=true`n", [System.Text.UTF8Encoding]::new($false))
    $properties = @'
server-ip=127.0.0.1
server-port=0
online-mode=true
enable-query=false
enable-rcon=false
max-players=1
view-distance=2
simulation-distance=2
level-seed=12345
level-type=minecraft:normal
level-name=world
sync-chunk-writes=true
'@
    [System.IO.File]::WriteAllText((Join-Path $directory 'server.properties'), $properties, [System.Text.UTF8Encoding]::new($false))
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.WorkingDirectory = $directory
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    if ($Native) {
        $startInfo.FileName = $binaryPath
        $arguments = @('-Xmx3g', 'nogui')
    } else {
        $planText = & $boomPath reference --lock $lockPath --game-dir $directory --dry-run
        if ($LASTEXITCODE -ne 0) { throw 'Cannot prepare reference JVM.' }
        $plan = ($planText -join "`n") | ConvertFrom-Json
        $startInfo.FileName = $plan.executable
        $arguments = @($plan.arguments | ForEach-Object { if ($_ -eq '-Xmx2G') { '-Xmx3G' } else { $_ } })
        if ($Name -eq 'jvm-create') { $arguments = @("-agentpath:${agent}=config-merge-dir=$metadataRoot") + $arguments }
    }
    foreach ($argument in $arguments) { $startInfo.ArgumentList.Add($argument) }
    $startInfo.ArgumentList.Insert(0,"-Djdk.net.unixdomain.tmpdir=$temporaryRoot")
    $startInfo.ArgumentList.Insert(0,"-Djava.io.tmpdir=$temporaryRoot")
    foreach ($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')) { $startInfo.Environment.Remove($key) | Out-Null }
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    $started = $false
    $ready = $false
    $readBlock = -not [bool]$ExpectedBlock
    $readScore = $ExpectedScore -lt 0
    $writeBlockOk = -not [bool]$WriteBlock
    $writeScoreOk = $WriteScore -lt 0
    $stopSent = $false
    $runtimeError = $false
    $lastCommand = [datetime]::MinValue
    $logPath = Join-Path $directory 'server.log'
    $writer = [System.IO.StreamWriter]::new($logPath, $false, [System.Text.UTF8Encoding]::new($false))
    $writer.AutoFlush = $true
    try {
        if (-not $process.Start()) { throw 'Cannot start world test server.' }
        $started = $true
        $readers = @($process.StandardOutput,$process.StandardError)
        $tasks = @($readers[0].ReadLineAsync(),$readers[1].ReadLineAsync())
        $deadline = [datetime]::UtcNow.AddSeconds($StageTimeoutSeconds)
        while ([datetime]::UtcNow -lt $deadline) {
            for ($index=0; $index -lt 2; $index++) {
                while ($null -ne $tasks[$index] -and $tasks[$index].IsCompleted) {
                    $line = $tasks[$index].GetAwaiter().GetResult()
                    if ($null -eq $line) { $tasks[$index] = $null; break }
                    $writer.WriteLine($line)
                    if ($line -match 'Done \(') { $ready = $true }
                    if ($line -match '\[Server\] BOOM_READ_BLOCK_OK') { $readBlock = $true }
                    if ($line -match '\[Server\] BOOM_READ_SCORE_OK') { $readScore = $true }
                    if ($line -match '\[Server\] BOOM_WRITE_BLOCK_OK') { $writeBlockOk = $true }
                    if ($line -match '\[Server\] BOOM_WRITE_SCORE_OK') { $writeScoreOk = $true }
                    if ($line -match 'UnsupportedFeatureError|Exception in thread|ERROR StatusLogger|could not find a logging implementation') { $runtimeError = $true }
                    $tasks[$index] = $readers[$index].ReadLineAsync()
                }
            }
            if ($process.HasExited -and $null -eq $tasks[0] -and $null -eq $tasks[1]) { break }
            if ($ready -and -not $stopSent -and -not $process.HasExited -and ([datetime]::UtcNow - $lastCommand).TotalSeconds -ge 1) {
                $commands = @('execute in minecraft:overworld run forceload add 0 0')
                if (-not $readBlock) { $commands += "execute in minecraft:overworld if block 0 100 0 minecraft:$ExpectedBlock run say BOOM_READ_BLOCK_OK" }
                if (-not $readScore) { $commands += "execute if score sentinel boom matches $ExpectedScore run say BOOM_READ_SCORE_OK" }
                if ($readBlock -and $readScore) {
                    if (-not $writeBlockOk) { $commands += "execute in minecraft:overworld run setblock 0 100 0 minecraft:$WriteBlock"; $commands += "execute in minecraft:overworld if block 0 100 0 minecraft:$WriteBlock run say BOOM_WRITE_BLOCK_OK" }
                    if (-not $writeScoreOk) { $commands += 'scoreboard objectives add boom dummy'; $commands += "scoreboard players set sentinel boom $WriteScore"; $commands += "execute if score sentinel boom matches $WriteScore run say BOOM_WRITE_SCORE_OK" }
                }
                if ($readBlock -and $readScore -and $writeBlockOk -and $writeScoreOk) { $commands += @('save-all flush','stop'); $stopSent = $true }
                foreach ($command in $commands) { $process.StandardInput.WriteLine($command) }
                $process.StandardInput.Flush()
                $lastCommand = [datetime]::UtcNow
            }
            Start-Sleep -Milliseconds 50
        }
        $completed = $process.HasExited
        $saved = Test-Path -LiteralPath (Join-Path $directory 'world\level.dat')
        $passed = $completed -and $process.ExitCode -eq 0 -and $ready -and $readBlock -and $readScore -and $writeBlockOk -and $writeScoreOk -and $stopSent -and $saved -and -not $runtimeError
        return [ordered]@{ stage=$Name; native=$Native; passed=$passed; ready=$ready; read_block=$readBlock; read_score=$readScore; write_block=$writeBlockOk; write_score=$writeScoreOk; clean_stop=$stopSent -and $completed; saved_world=$saved; runtime_error=$runtimeError; directory=$directory; log=$logPath }
    } finally {
        if ($started -and -not $process.HasExited) {
            try { $process.StandardInput.WriteLine('stop'); $process.StandardInput.Flush() } catch { }
            if (-not $process.WaitForExit(5000)) { $process.Kill($true); $process.WaitForExit() }
        }
        $writer.Dispose()
        $process.Dispose()
    }
}

try {
    $stages += Invoke-WorldStage 'jvm-create' $false '' '' -1 'diamond_block' 42
    if ($stages[-1].passed) { $stages += Invoke-WorldStage 'native-roundtrip' $true (Join-Path $stages[-1].directory 'world') 'diamond_block' 42 'emerald_block' 84 }
    if ($stages.Count -eq 2 -and $stages[-1].passed) { $stages += Invoke-WorldStage 'jvm-reopen' $false (Join-Path $stages[-1].directory 'world') 'emerald_block' 84 '' -1 }
} finally {
    $report = [ordered]@{ game_version='1.21.1'; scope='server world and storage roundtrip'; full_game_validated=$false; input_fingerprint=$inputs.fingerprint; java_version=$inputs.java.version; binary=$binaryPath; metadata=$metadataRoot; temporary_directory=$temporaryRoot; run_directory=$runRoot; stages=$stages; passed=$stages.Count -eq 3 -and @($stages | Where-Object { -not $_.passed }).Count -eq 0 }
    $reportJson = $report | ConvertTo-Json -Depth 7
    [System.IO.File]::WriteAllText((Join-Path $runRoot 'roundtrip-result.json'),$reportJson,[System.Text.UTF8Encoding]::new($false))
    Write-Output $reportJson
}
if (-not $report.passed) { exit 1 }
