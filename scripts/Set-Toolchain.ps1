param(
    [string]$Java = 'D:\Dev\Java\jdk-21\bin\java.exe',
    [string]$NativeImage = ''
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$javaPath = (Resolve-Path -LiteralPath $Java).Path
if (-not (Test-Path -LiteralPath $javaPath -PathType Leaf)) { throw 'Java executable is missing.' }
$nativeImagePath = $null
if ($NativeImage) {
    $nativeImagePath = (Resolve-Path -LiteralPath $NativeImage).Path
    if (-not (Test-Path -LiteralPath $nativeImagePath -PathType Leaf)) { throw 'Native Image executable is missing.' }
} elseif (Test-Path -LiteralPath 'D:\Dev\GraalVM\jdk-21\bin\native-image.cmd' -PathType Leaf) {
    $nativeImagePath = 'D:\Dev\GraalVM\jdk-21\bin\native-image.cmd'
}

$cacheDirectory = Join-Path $projectRoot '.boom'
[System.IO.Directory]::CreateDirectory($cacheDirectory) | Out-Null
$configurationPath = Join-Path $cacheDirectory 'toolchain.json'
$configuration = [ordered]@{
    java = $javaPath
    installed_tool_root = 'D:\Dev'
}
if ($nativeImagePath) { $configuration.Add('native_image',$nativeImagePath) }
[System.IO.File]::WriteAllText($configurationPath, ($configuration | ConvertTo-Json), [System.Text.UTF8Encoding]::new($false))
Write-Output "Saved local tool paths to $configurationPath"
