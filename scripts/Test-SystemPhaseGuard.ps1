param([string]$Boom='dist\boom.exe',[string]$MetadataLock='.boom\locks\server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
$root=Join-Path (Get-Location) ('.boom/system-phase-guard-tests/'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$source=Join-Path $root 'PhaseGuard.java'
[IO.File]::WriteAllText($source,@'
public final class PhaseGuard {
    public static int stream() { return System.out == null ? 1 : 0; }
    public static int property() { return System.getProperty("java.version").length(); }
}
'@,[Text.UTF8Encoding]::new($false))
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe') --release 21 -proc:none -d $classes $source
if($LASTEXITCODE -ne 0){throw 'System phase guard javac failed'}
$checks=[Collections.Generic.List[object]]::new()
foreach($method in @('stream','property')){
    $out=Join-Path $root $method
    $text=& $Boom compile-program --class-file (Join-Path $classes 'PhaseGuard.class') --entry-class PhaseGuard --method $method --metadata-lock $MetadataLock --jdk-base $JdkBase --output $out --assemble 2>&1
    $code=$LASTEXITCODE;$reason=($text|ForEach-Object ToString) -join "`n"
    if($code -eq 0 -or (Test-Path $out) -or $reason -notmatch 'System .*startup phases'){throw "Uninitialized System state was not guarded: $method, $reason"}
    $checks.Add(@{method=$method;compiler_exit_code=$code;reason=$reason;no_executable_output=$true})
}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'System phase guard compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;negative_checks=@($checks.ToArray());uninitialized_standard_stream_not_returned_as_normal=$true;uninitialized_properties_not_executed=$true;passed=$true;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 7
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText('.boom/latest-system-phase-guard.txt',$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
exit 0
