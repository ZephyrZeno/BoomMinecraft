param([Parameter(Mandatory=$true)][string]$Directory,[Parameter(Mandatory=$true)][string]$AcceptedVerificationSha256,[ValidateSet('scoped-memory','throwable')][string]$Mode)
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=Join-Path $project ('.boom/normal-native-source-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'prepare-normal-native-source-probe.py') --directory $Directory --accepted-verification-sha256 $AcceptedVerificationSha256 --mode $Mode --output "$root/source.json" > "$root/prepare.log" 2> "$root/prepare.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/prepare.err" -Tail 14;throw 'Normal native source test preparation failed'}
$m=Get-Content -LiteralPath "$root/source.json" -Raw|ConvertFrom-Json
function Assert-Inputs {foreach($r in $m.inputs){if((Get-Item -LiteralPath $r.path).Length -ne $r.digest.size -or (Get-FileHash -LiteralPath $r.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $r.digest.sha256){throw ('Normal native source input changed: '+$r.path)}}}
Assert-Inputs
Add-Type -Path (Join-Path $project 'tests/host/NormalNativeSourceProbe.cs')
$v=[BoomNormalNativeSourceProbe]::Run("$root/source.json")
Assert-Inputs
$result=[ordered]@{passed=$true;mode=$Mode;source_native_entries_exercised=1;prepared_receiver_or_frame_objects=$false;original_Java_executed=$true;source_configuration="$root/source.json";source_sha256=(Get-FileHash -LiteralPath "$root/source.json" -Algorithm SHA256).Hash.ToLowerInvariant();full_VM_bootstrap=$false;stack_roots=$false;automatic_gc=$false;game_started=$false;world_created=$false;run_directory=$root}
if($Mode -eq 'scoped-memory'){
    $result.scope='original_ScopedMemoryAccess_cold_initializer_singleton_constructor_registration_and_getter_via_original_Buffer_initializer'
    $result.cold_original_class_initializations=$v[0];$result.original_singleton_constructors=$v[1];$result.error_checks=$v[2];$result.workers=$v[3];$result.parallel_registrations=$v[4];$result.original_getter_via_Buffer_initializer=$v[5];$result.cold_registration_workers=$v[6];$result.close_scope_implemented=$false;$result.thread_handshake_implemented=$false
}else{
    $result.scope='original_Unsafe_throwIllegalAccessError_explicit_Java_Error_construction_throw_and_bounded_native_backtrace'
    $result.cold_original_Throwable_initializations=$v[0];$result.visible_original_caller_frames=$v[1];$result.workers=$v[2];$result.parallel_original_Java_throws=$v[3];$result.Java_StackTraceElement_materialization=$false;$result.implicit_exception_factory=$false
}
$json=$result|ConvertTo-Json -Depth 5;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
