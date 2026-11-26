param([Parameter(Mandatory=$true)][string]$Directory,[Parameter(Mandatory=$true)][string]$AcceptedVerificationSha256,
[ValidateSet('DescriptorFirst','OutputFirst','InputFirst')][string]$InitializationOrder='DescriptorFirst',[switch]$VerifyClassMonitor)
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if($VerifyClassMonitor -and $InitializationOrder -ne 'OutputFirst'){throw 'Cold Class monitor contention test requires OutputFirst initialization'}
$root=Join-Path $project ('.boom/file-bootstrap-source-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
$prepareArgs=@((Join-Path $PSScriptRoot 'prepare-file-bootstrap-source-test.py'),'--directory',$Directory,'--accepted-verification-sha256',$AcceptedVerificationSha256,'--output',"$root/source.json")
if($VerifyClassMonitor){$prepareArgs+='--verify-class-monitor'}
& D:/Dev/Python312/python.exe @prepareArgs > "$root/prepare.log" 2> "$root/prepare.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/prepare.err" -Tail 16;throw 'Original file source preparation failed'}
$m=Get-Content -LiteralPath "$root/source.json" -Raw|ConvertFrom-Json
function Assert-Inputs {foreach($r in $m.inputs){if((Get-Item -LiteralPath $r.path).Length -ne $r.digest.size -or (Get-FileHash -LiteralPath $r.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $r.digest.sha256){throw ('Original file input changed: '+$r.path)}}}
Assert-Inputs
Add-Type -Path (Join-Path $project 'tests/host/FileBootstrapSourceProbe.cs')
$first=switch($InitializationOrder){'OutputFirst'{1};'InputFirst'{0};default{2}}
$v=[BoomFileBootstrapSourceProbe]::Run("$root/source.json",$first,[bool]$VerifyClassMonitor)
Assert-Inputs
$result=[ordered]@{passed=$true;scope='six_original_file_and_byte_order_bindings_and_cold_original_Java_initializers_and_standard_descriptor_constructors';cold_original_class_initializations=$v[0];original_standard_descriptor_constructors=$v[1];descriptor_cases=$v[2];workers=$v[3];parallel_calls=$v[4];
source_native_entries_exercised=6;initialization_order=$(switch($InitializationOrder){'OutputFirst'{@('FileOutputStream','FileInputStream','FileDescriptor','StringUTF16')};'InputFirst'{@('FileInputStream','FileOutputStream','FileDescriptor','StringUTF16')};default{@('FileDescriptor','FileInputStream','FileOutputStream','StringUTF16')}});alternate_cold_initialization_orders_verified=($InitializationOrder -ne 'DescriptorFirst');normal_Class_monitor_contention_verified=($v[5] -eq 1);observed_source_monitor_waiters=$v[6];normal_Class_monitor_source=$m.normal_Class_monitor_source;original_UTF16_byte_shift_initialization=$true;prepared_descriptor_or_module_objects=$false;source_configuration="$root/source.json";source_sha256=(Get-FileHash -LiteralPath "$root/source.json" -Algorithm SHA256).Hash.ToLowerInvariant();full_VM_bootstrap=$false;file_reads_or_writes_executed=$false;game_started=$false;world_created=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 5;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
