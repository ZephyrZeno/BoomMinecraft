param([Parameter(Mandatory=$true)][string]$Directory,[Parameter(Mandatory=$true)][string]$AcceptedVerificationSha256,[ValidateRange(32,512)][int]$HeapMB=128)
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=(Resolve-Path -LiteralPath $Directory).Path
$allowed=[IO.Path]::GetFullPath((Join-Path $project '.boom/diagnostic-startup'))+[IO.Path]::DirectorySeparatorChar
if(-not $root.StartsWith($allowed,[StringComparison]::OrdinalIgnoreCase)){throw 'Recovered execution must remain in project startup diagnostics'}
$proofPath=Join-Path $root 'selection-verification.json';$proof=Get-Content -LiteralPath $proofPath -Raw|ConvertFrom-Json
if((Get-FileHash -LiteralPath $proofPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $AcceptedVerificationSha256.ToLowerInvariant() -or -not $proof.verified -or -not $proof.diagnostic_only -or $proof.source_closure_complete){throw 'Explicitly accepted independent verification differs'}
if(Test-Path -LiteralPath (Join-Path $root 'execution.json')){throw 'An executed round is immutable; resume the startup driver'}
$diagnostic=Get-Content -LiteralPath (Join-Path $root 'diagnostic.json') -Raw|ConvertFrom-Json
$runtime=Split-Path $diagnostic.global_provider_identity.runtime_dll -Parent
if((Get-FileHash -LiteralPath $diagnostic.global_provider_identity.runtime_dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $diagnostic.global_provider_identity.runtime_sha256){throw 'Accepted runtime changed'}
$image=Join-Path $root 'diagnostic-image.dll';$imageHash=(Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash.ToLowerInvariant()
$start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=(Get-Process -Id $PID).Path;$start.WorkingDirectory=$root;$start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
foreach($a in @('-NoProfile','-File',(Join-Path $PSScriptRoot 'Run-DiagnosticImage.ps1'),'-Directory',$root,'-Runtime',$runtime,'-HeapMB',"$HeapMB")){$start.ArgumentList.Add($a)}
$process=[Diagnostics.Process]::new();$process.StartInfo=$start
try{
    if(-not $process.Start()){throw 'Cannot start owned recovered diagnostic execution'}
    $out_=$process.StandardOutput.ReadToEndAsync();$err_=$process.StandardError.ReadToEndAsync()
    if(-not $process.WaitForExit(45000)){$process.Kill($true);throw 'Owned recovered execution exceeded 45 seconds'}
    [IO.File]::WriteAllText((Join-Path $root 'execution.out.log'),$out_.GetAwaiter().GetResult(),[Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText((Join-Path $root 'execution.err.log'),$err_.GetAwaiter().GetResult(),[Text.UTF8Encoding]::new($false))
    if($process.ExitCode -ne 0){throw 'Owned recovered diagnostic execution failed; inspect execution.err.log'}
}finally{$process.Dispose()}
if((Get-FileHash -LiteralPath $image -Algorithm SHA256).Hash.ToLowerInvariant() -ne $imageHash -or (Get-FileHash -LiteralPath $proofPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $AcceptedVerificationSha256.ToLowerInvariant()){throw 'Accepted execution input changed'}
Get-Content -LiteralPath (Join-Path $root 'execution.json') -Raw
