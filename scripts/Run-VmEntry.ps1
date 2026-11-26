param([Parameter(Mandatory=$true)][string]$Directory,[Parameter(Mandatory=$true)][string]$AcceptedVerificationSha256,[switch]$ObserveSourceAdmissions)
$ErrorActionPreference='Stop';$root=(Resolve-Path -LiteralPath $Directory).Path
$allowed=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../.boom/vm-entry-images'))+[IO.Path]::DirectorySeparatorChar
if(-not $root.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase)){throw 'Native entry execution requires isolated project output'}
$proofPath=Join-Path $root 'verification.json';$proof=Get-Content -LiteralPath $proofPath -Raw|ConvertFrom-Json
if((Get-FileHash -LiteralPath $proofPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $AcceptedVerificationSha256 -or -not $proof.verified -or $proof.managed_execution_host -or $proof.full_VM_bootstrap -or $proof.game_started){throw 'Explicitly accepted native entry verification differs'}
$manifestPath=Join-Path $root 'vm-entry.json';$m=Get-Content -LiteralPath $manifestPath -Raw|ConvertFrom-Json
if((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $proof.source_manifest_sha256){throw 'Native entry source manifest changed'}
if((Test-Path -LiteralPath (Join-Path $root 'execution.json')) -or (Test-Path -LiteralPath (Join-Path $root 'vm-entry-status.bin'))){throw 'A native process execution record is immutable'}
$records=@($m.inputs)+@($m.executable,$m.runtime,$m.assembly,$m.link_response)+@($m.reassembled_objects)
function Assert-Inputs {foreach($r in $records){if((Get-Item -LiteralPath $r.path).Length -ne $r.digest.size -or (Get-FileHash -LiteralPath $r.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $r.digest.sha256){throw ('Native VM entry input changed: '+$r.path)}}}
$decoderPath=Join-Path $PSScriptRoot 'decode-vm-entry-report.py'
$records+=([pscustomobject]@{path=$decoderPath;digest=[pscustomobject]@{size=(Get-Item -LiteralPath $decoderPath).Length;sha256=(Get-FileHash -LiteralPath $decoderPath -Algorithm SHA256).Hash.ToLowerInvariant()}})
Assert-Inputs
$start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$m.executable.path;$start.WorkingDirectory=$root;$start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
$process=[Diagnostics.Process]::new();$process.StartInfo=$start
try{
    if(-not $process.Start()){throw 'Cannot start the owned assembly VM process'}
    $out_=$process.StandardOutput.ReadToEndAsync();$err_=$process.StandardError.ReadToEndAsync()
    if(-not $process.WaitForExit(45000)){$process.Kill($true);throw 'Owned native VM bootstrap prefix exceeded 45 seconds'}
    [IO.File]::WriteAllText((Join-Path $root 'process.out.log'),$out_.GetAwaiter().GetResult(),[Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $root 'process.err.log'),$err_.GetAwaiter().GetResult(),[Text.UTF8Encoding]::new($false))
    $exitCode=$process.ExitCode
}finally{$process.Dispose()}
Assert-Inputs
$decodeArgs=@($decoderPath,'--manifest',$manifestPath,'--report',(Join-Path $root 'vm-entry-status.bin'),
'--exit-code',[string]$exitCode,'--accepted-verification-sha256',$AcceptedVerificationSha256,'--output',(Join-Path $root 'execution.json'))
if($ObserveSourceAdmissions){$decodeArgs+='--observe-source-admissions'}
& D:/Dev/Python312/python.exe @decodeArgs
if($LASTEXITCODE -ne 0){throw 'Native process report protocol validation failed; binary report is preserved'}
Assert-Inputs
