param([string]$Boom='target/release/boom.exe',[string]$Runtime='.boom/assembly-runtime-v71/boom-runtime.dll')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/boot-unnamed-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& ./scripts/Test-ModuleObjects.ps1 -Boom $Boom > "$root/module-test.log" 2>&1
if($LASTEXITCODE -ne 0){throw 'Module original-constructor regression failed'}
$fixture=(Get-Content .boom/latest-module-object-test.txt -Raw).Trim();$p=Get-Content "$fixture/program/program.json" -Raw|ConvertFrom-Json
if(-not ('BoomModuleObjectsProbe' -as [type])){Add-Type -Path tests/host/ModuleObjectsProbe.cs}
[BoomModuleObjectsProbe]::RunBootstrap($p.compilation.dll,[IO.Path]::GetFullPath($Runtime))
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Bootstrap compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;full_runtime_sha256=(Get-FileHash $Runtime).Hash.ToLowerInvariant();runtime_language='assembly';original_Module_constructor_executed=$true;bootstrap_Module_canonical_publication_and_load_checked=$true;workers=8;parallel_publications=1024;uninitialized_wrong_owner_named_application_and_root_bounds_checked=$true;duplicate_Module_cannot_replace_canonical_VM_root=$true;VM_root_survives_quiescent_GC_after_Java_fixture_cell_cleared=$true;BootLoader_descriptor_and_VM_root_table_are_fixtures=$true;original_BootLoader_Java_initializer_executed=$false;named_Module_bootstrap_complete=$false;System_boot_phases_completed=$false;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;fixture_directory=$fixture;run_directory=$root}
$json=$report|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-boot-unnamed-test.txt',$root);Write-Output $json
exit 0
