param(
    [ValidateSet(21,25)][int]$Major = 25,
    [string]$ToolsRoot = 'D:\Dev'
)

$ErrorActionPreference = 'Stop'
$toolRoot = [System.IO.Path]::GetFullPath($ToolsRoot).TrimEnd('\')
$graalRoot = Join-Path $toolRoot 'GraalVM'
$destination = [System.IO.Path]::GetFullPath((Join-Path $graalRoot "jdk-$Major"))
$allowedRoot = $toolRoot + '\'
if (-not $destination.StartsWith($allowedRoot,[System.StringComparison]::OrdinalIgnoreCase)) { throw 'Tool destination escaped the tools root.' }
if (Test-Path -LiteralPath $destination) {
    $existing = Join-Path $destination 'bin\native-image.cmd'
    if (-not (Test-Path -LiteralPath $existing -PathType Leaf)) { throw 'Incomplete tool installation exists; refusing to overwrite it.' }
    Write-Output $existing
    return
}
$downloadRoot = Join-Path $graalRoot 'downloads'
[System.IO.Directory]::CreateDirectory($downloadRoot) | Out-Null
$url = "https://download.oracle.com/graalvm/$Major/latest/graalvm-jdk-${Major}_windows-x64_bin.zip"
$expected = ((Invoke-WebRequest -Uri ($url + '.sha256') -TimeoutSec 30).Content).Trim().Split(' ')[0].ToLowerInvariant()
if ($expected -notmatch '^[a-f0-9]{64}$') { throw 'Invalid official checksum.' }
$archive = Join-Path $downloadRoot ("graalvm-jdk-$Major-" + $expected.Substring(0,12) + '.zip')
if (-not (Test-Path -LiteralPath $archive)) {
    $ProgressPreference = 'SilentlyContinue'
    $partial = $archive + '.part'
    Invoke-WebRequest -Uri $url -OutFile $partial -TimeoutSec 600
    if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'GraalVM download checksum mismatch.' }
    Move-Item -LiteralPath $partial -Destination $archive
}
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected) { throw 'Cached GraalVM checksum mismatch.' }
$staging = Join-Path $graalRoot ('.staging-' + [guid]::NewGuid().ToString('N'))
[System.IO.Directory]::CreateDirectory($staging) | Out-Null
[System.IO.Compression.ZipFile]::ExtractToDirectory($archive,$staging)
$candidates = @(Get-ChildItem -LiteralPath $staging -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'bin\native-image.cmd') })
if ($candidates.Count -ne 1) { throw 'Unexpected GraalVM archive layout.' }
$source = (Resolve-Path -LiteralPath $candidates[0].FullName).Path
$stagingPrefix = (Resolve-Path -LiteralPath $staging).Path.TrimEnd('\') + '\'
if (-not $source.StartsWith($stagingPrefix,[System.StringComparison]::OrdinalIgnoreCase) -or -not $destination.StartsWith($allowedRoot,[System.StringComparison]::OrdinalIgnoreCase)) { throw 'Refusing tool move outside the verified paths.' }
Move-Item -LiteralPath $source -Destination $destination
$receipt = [ordered]@{ url=$url; sha256=$expected; installed_directory=$destination }
[System.IO.File]::WriteAllText((Join-Path $destination 'boom-installation.json'),($receipt | ConvertTo-Json),[System.Text.UTF8Encoding]::new($false))
Write-Output (Join-Path $destination 'bin\native-image.cmd')
