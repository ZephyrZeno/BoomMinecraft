param([string]$Output='dist')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Push-Location -LiteralPath $projectRoot
try {
    & cargo build --release --locked --bin boom
    if($LASTEXITCODE -ne 0) { throw 'Launcher build failed.' }
    $destination=[IO.Path]::GetFullPath($Output)
    [IO.Directory]::CreateDirectory($destination) | Out-Null
    foreach($file in @('boom.exe')) {
        Copy-Item -LiteralPath (Join-Path $projectRoot "target\release\$file") -Destination (Join-Path $destination $file) -Force
    }
    $licenses=Join-Path $destination 'licenses'
    [IO.Directory]::CreateDirectory($licenses)|Out-Null
    Copy-Item -LiteralPath (Join-Path $projectRoot 'third_party\unicode\LICENSE.txt') -Destination (Join-Path $licenses 'unicode.txt') -Force
    $csc=Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
    if(-not (Test-Path -LiteralPath $csc)) { throw 'The existing Windows .NET Framework C# compiler is missing.' }
    & $csc /nologo /target:winexe /platform:x64 /optimize+ /codepage:65001 "/out:$(Join-Path $destination 'BoomLauncher.exe')" /reference:System.Drawing.dll /reference:System.Windows.Forms.dll /reference:System.Core.dll /reference:System.Web.Extensions.dll (Join-Path $projectRoot 'launcher\Launcher.cs')
    if($LASTEXITCODE -ne 0) { throw 'Launcher UI compilation failed.' }
    & (Join-Path $PSScriptRoot 'Build-NativeProbe.ps1') -Output (Join-Path $destination 'native') -Boom (Join-Path $destination 'boom.exe')
    Write-Output "Launcher: $(Join-Path $destination 'BoomLauncher.exe')"
} finally { Pop-Location }
