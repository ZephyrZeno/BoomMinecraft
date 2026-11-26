param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/windows-file-system-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-windows-file-system-test.txt',$root)
& $Boom inspect-windows-file-system --lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root inspection) > (Join-Path $root inspection.json)
if($LASTEXITCODE -ne 0){throw 'Windows file system contract inspection failed'}
& D:/Dev/Python312/python.exe scripts/verify-windows-file-system.py (Join-Path $root inspection/inspection.json) > (Join-Path $root source-contract.json)
if($LASTEXITCODE -ne 0){throw 'Windows file system independent source verification failed'}
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -d (Join-Path $root classes) java/reference/WindowsFileSystemReference.java
if($LASTEXITCODE -ne 0){throw 'Windows file system oracle javac failed'}
& $inputs.java.executable --add-opens=java.base/java.io=ALL-UNNAMED -cp (Join-Path $root classes) WindowsFileSystemReference > (Join-Path $root reference.txt) 2> (Join-Path $root reference.err)
if($LASTEXITCODE -ne 0 -or (Get-Content (Join-Path $root reference.txt)|Select-Object -Last 1) -ne 'init_calls=256;private_final_String_path=1'){throw 'Windows file system JVM native oracle failed'}
& scripts/Build-AssemblyRuntime.ps1 -Output (Join-Path $root runtime) > (Join-Path $root runtime.log) 2>&1
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root runtime.log) -Tail 18;throw 'Windows file system assembly runtime build failed'}
$p=Get-Content (Join-Path $root inspection/inspection.json) -Raw|ConvertFrom-Json
Add-Type -Path tests/host/WindowsFileSystemProbe.cs
[BoomWindowsFileSystemProbe]::Run((Join-Path $root runtime/boom-runtime.dll),[uint64]$p.plan.file_layout.payload_bytes,[uint32]$p.plan.file_layout.reference_prefix_fields,[uint32]$p.plan.file_layout.fields.Count,[uint32]$p.plan.path_offset)
& D:/Dev/Python312/python.exe scripts/make-platform-private-fixtures.py (Join-Path $root forged)
if($LASTEXITCODE -ne 0){throw 'Private Windows file system fixture generation failed'}
& $Boom compile-program --class-file (Join-Path $root forged/PrivateWinFsInit.class) --entry-class dev/boom/platform/PrivateWinFsInit --method run --descriptor '()V' --metadata-lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root rejected) > (Join-Path $root rejected.json) 2> (Join-Path $root rejected.err)
if($LASTEXITCODE -eq 0 -or (Get-Content (Join-Path $root rejected.err) -Raw) -notmatch 'WinNTFileSystem.initIDs is private'){throw 'Application private Windows file system native was not rejected'}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Windows file system compiler changed during tests'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';VM_pool_uses_original_compact_File_layout=$true;File_path_slot_validated=$true;Windows_final_path_function_and_module_match_OS=$true;workers=8;parallel_native_init_calls=4096;idempotent_JVM_and_ASM_init_calls=256;pending_context_and_bad_metadata_checked=$true;application_private_init_call_rejected=$true;VM_metadata_storage_is_explicit_fixture=$true;original_Java_WinNTFileSystem_initializer_executed=$false;original_Java_File_initializer_executed=$false;compiler_requires_File_initialization_before_native_call=$true;native_file_operations_complete=$false;automatic_gc=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-windows-file-system-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
