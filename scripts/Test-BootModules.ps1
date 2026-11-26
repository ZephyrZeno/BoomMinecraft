param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\client.json',[string]$OtherLock='.boom\locks\server.json')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$output=Join-Path $projectRoot ('.boom\jdk-module-tests\'+[guid]::NewGuid().ToString('N'))
& python -X utf8 (Join-Path $projectRoot 'tests\metadata\boot_modules.py') --boom $Boom --lock $MetadataLock --other-lock $OtherLock --output $output
exit $LASTEXITCODE
