param([Parameter(Mandatory=$true)][string]$PreparedSource,[Parameter(Mandatory=$true)][string]$WideningRun)
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$prepared=(Resolve-Path -LiteralPath $PreparedSource).Path;$wide=(Resolve-Path -LiteralPath $WideningRun).Path
$m=Get-Content -LiteralPath (Join-Path $prepared 'prepared.json') -Raw|ConvertFrom-Json
function Assert-CapturedInputs {
    foreach($input_ in @($m.inputs)+@($m.generated_artifacts)){
        if((Get-Item -LiteralPath $input_.path).Length -ne $input_.digest.size -or (Get-FileHash -LiteralPath $input_.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $input_.digest.sha256){throw ('Accepted constructor binding input changed: '+$input_.path)}
    }
}
Assert-CapturedInputs
$oracle=Join-Path $wide 'oracle.tsv';$oracleHash=(Get-FileHash -LiteralPath $oracle -Algorithm SHA256).Hash.ToLowerInvariant()
$wideResult=Get-Content -LiteralPath (Join-Path $wide 'result.json') -Raw|ConvertFrom-Json
if(-not $wideResult.passed){throw 'Independent constructor conversion reference was not accepted'}
$root=Join-Path $project ('.boom/constructor-invocation-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
Add-Type -Path (Join-Path $project 'tests/host/ConstructorCallsiteProbe.cs')
$values=[BoomConstructorCallsiteProbe]::RunNative($m.runtime,(Join-Path $m.image_directory 'diagnostic-image.dll'),(Join-Path $prepared 'source.json'),(Join-Path $prepared 'boxes.json'),$oracle,(Join-Path $prepared 'bindings.json'))
Assert-CapturedInputs
if((Get-FileHash -LiteralPath $oracle -Algorithm SHA256).Hash.ToLowerInvariant() -ne $oracleHash){throw 'Constructor conversion reference changed during execution'}
$result=[ordered]@{passed=$true;scope='two_original_native_constructor_entries_with_normal_Constructor_objects_and_original_Java_bodies';source_sites=$values[0];accepted_primitive_constructors=$values[1];rejected_primitive_arguments=$values[2];cold_original_class_initializations=$values[3];
original_constructor_body_errors_preserved_without_InvocationTargetException=$values[4];pre_call_errors=$values[5];workers=$values[6];parallel_calls=$values[7];first_native_calls=$values[8];second_native_calls=$values[9];
prepared_source=(Join-Path $prepared 'prepared.json');prepared_sha256=(Get-FileHash -LiteralPath (Join-Path $prepared 'prepared.json') -Algorithm SHA256).Hash.ToLowerInvariant();oracle_sha256=$oracleHash;fixture_only=$true;full_module_bootstrap=$false;exception_wrapping_complete=$false;all_native_frames=$false;game_started=$false;world_created=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 6;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
