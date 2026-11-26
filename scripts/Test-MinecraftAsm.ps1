param([string]$Boom='target\release\boom.exe',[string]$Lock='.boom\locks\server.json')

$ErrorActionPreference='Stop'
$projectRoot=[System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$boomPath=(Resolve-Path -LiteralPath $Boom).Path
& $boomPath verify --lock $Lock | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Official inputs failed verification.' }
$inputs=Get-Content -LiteralPath $Lock -Raw | ConvertFrom-Json
if ($inputs.game_version -ne '1.21.1' -or $inputs.side -ne 'server') { throw 'This proof requires the 1.21.1 server input.' }
$root=Join-Path $projectRoot ('.boom\minecraft-asm-proof\'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'oracle'
[System.IO.Directory]::CreateDirectory($classes) | Out-Null
$game=@($inputs.files | Where-Object { $_.role -eq 'server-game' })[0]
$classFile=Join-Path $root 'axy$b.class'
$archive=[System.IO.Compression.ZipFile]::OpenRead($game.path)
try { $entry=$archive.GetEntry('axy$b.class'); if (-not $entry) { throw 'Pinned Minecraft color class is missing.' }; [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry,$classFile,$false) } finally { $archive.Dispose() }
$javac=Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe'
& $javac --release 21 -encoding UTF-8 -d $classes (Join-Path $projectRoot 'java\subset\dev\boom\subset\MethodOracle.java')
if ($LASTEXITCODE -ne 0) { throw 'Cannot compile reference oracle.' }
$methods=@(@{name='alpha';symbol='a';descriptor='(I)I'},@{name='red';symbol='b';descriptor='(I)I'},@{name='green';symbol='c';descriptor='(I)I'},@{name='blue';symbol='d';descriptor='(I)I'},@{name='opaque';symbol='e';descriptor='(I)I'},@{name='color';symbol='a';descriptor='(IIII)I'})
$cases=[System.Collections.Generic.List[object]]::new()
$bounds=@([int]::MinValue,[int]::MaxValue,-1,0,1,127,255,256,287454020,-16711936,31,32)
$manifests=@{}
foreach ($method in $methods) {
    $output=Join-Path $root $method.name
    & $boomPath compile-asm --class-file $classFile --method $method.symbol --descriptor $method.descriptor --output $output --assemble | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Cannot compile original Minecraft method $($method.name)" }
    $manifests[$method.name]=Join-Path $output 'compilation.json'
    for ($index=0; $index -lt $bounds.Count; $index++) {
        $values=if ($method.name -eq 'color') { @($bounds[$index],$bounds[($index+1)%$bounds.Count],$bounds[($index+2)%$bounds.Count],$bounds[($index+3)%$bounds.Count]) } else { @($bounds[$index]) }
        $cases.Add([pscustomobject]@{method=$method.name;symbol=$method.symbol;values=$values})
    }
}
$paths=@($classes)+@($inputs.classpath | ForEach-Object { $id=$_; @($inputs.files | Where-Object { $_.id -eq $id })[0].path })
$info=[System.Diagnostics.ProcessStartInfo]::new()
$info.FileName=$inputs.java.executable
$info.UseShellExecute=$false
$info.CreateNoWindow=$true
$info.RedirectStandardInput=$true
$info.RedirectStandardOutput=$true
$info.RedirectStandardError=$true
foreach ($argument in @('-cp',($paths -join ';'),'dev.boom.subset.MethodOracle','axy$b')) { $info.ArgumentList.Add($argument) }
foreach ($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')) { $info.Environment.Remove($key) | Out-Null }
$oracle=[System.Diagnostics.Process]::new(); $oracle.StartInfo=$info; $started=$false
try {
    $started=$oracle.Start(); if (-not $started) { throw 'Cannot start Minecraft method oracle.' }
    $stdout=$oracle.StandardOutput.ReadToEndAsync(); $stderr=$oracle.StandardError.ReadToEndAsync()
    foreach ($case in $cases) { $oracle.StandardInput.WriteLine((@($case.symbol)+@($case.values) -join ' ')) }
    $oracle.StandardInput.Close()
    if (-not $oracle.WaitForExit(30000)) { $oracle.Kill($true); $oracle.WaitForExit(); throw 'Oracle timeout.' }
    if ($oracle.ExitCode -ne 0) { throw $stderr.GetAwaiter().GetResult() }
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[System.StringSplitOptions]::RemoveEmptyEntries) | ForEach-Object { [int]$_.Trim() })
} finally { if ($started -and -not $oracle.HasExited) { $oracle.Kill($true); $oracle.WaitForExit() }; $oracle.Dispose() }
if ($expected.Count -ne $cases.Count) { throw 'Oracle result count mismatch.' }
$failures=@()
for ($index=0; $index -lt $cases.Count; $index++) {
    $case=$cases[$index]
    $arguments=@('execute-asm','--manifest',$manifests[$case.method])+@($case.values | ForEach-Object { "--arg=$_" })
    $text=& $boomPath @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Native method execution failed.' }
    $actual=($text | ConvertFrom-Json).result
    if ($actual -ne $expected[$index]) { $failures+=@{case=$case;expected=$expected[$index];actual=$actual} }
}
$report=[ordered]@{ game_version='1.21.1'; input_fingerprint=$inputs.fingerprint; backend='boom-i32-v2-masm-x64'; original_class='net.minecraft.util.FastColor$ARGB32'; obfuscated_class='axy$b'; original_methods=$methods.Count; differential_cases=$cases.Count; failures=$failures; passed=$failures.Count -eq 0; full_game_compiled=$false; run_directory=$root }
$json=$report | ConvertTo-Json -Depth 7
[System.IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[System.Text.UTF8Encoding]::new($false))
Write-Output $json
if (-not $report.passed) { exit 1 }
