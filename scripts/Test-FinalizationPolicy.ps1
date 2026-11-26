param([string]$Boom='target/release/boom.exe',[string]$Runtime='.boom/assembly-runtime-v71/boom-runtime.dll',[string]$ExistingProgram='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/finalization-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json
$program=if($ExistingProgram){[IO.Path]::GetFullPath($ExistingProgram)}else{Join-Path $root program}
if(-not $ExistingProgram){& $Boom compile-locked-program --lock .boom/locks/server.json --jdk-base $base --entry-class java/lang/ref/Finalizer --method getQueue --descriptor '()Ljava/lang/ref/ReferenceQueue;' --output $program --assemble > "$root/compile.json" 2> "$root/compile.err";if($LASTEXITCODE -ne 0){Get-Content "$root/compile.err" -Tail 8;throw 'Finalizer original Java compilation failed'}}
$p=Get-Content "$program/program.json" -Raw|ConvertFrom-Json
$b=@($p.vm_registration|Where-Object operation -eq FinalizationEnabled)
if($b.Count -ne 1 -or $b[0].finalization_policy -ne 'disabled' -or $b[0].registered_name -ne 'isFinalizationEnabled' -or $b[0].origin.source_id -ne 'jdk:java.base' -or $b[0].caller.sha256 -ne $b[0].origin.sha256){throw 'Finalizer policy provenance differs'}
$c=@($p.classes|Where-Object name -eq java/lang/ref/Finalizer)[0]
$q=@($p.classes|Where-Object name -eq java/lang/ref/NativeReferenceQueue)[0]
function Slot($name){[uint32]@($c.fields|Where-Object name -eq $name)[0].index}
Add-Type -Path tests/host/FinalizerProbe.cs
[BoomFinalizerProbe]::Run($p.compilation.dll,[IO.Path]::GetFullPath($Runtime),[uint32]$c.id,(Slot ENABLED),(Slot queue),(Slot lock),(Slot unfinalized),[uint32]$q.id)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Finalizer compiler changed'}
$report=[ordered]@{compiler_sha256=$sha;full_runtime_sha256=(Get-FileHash $Runtime).Hash.ToLowerInvariant();program=$program;runtime_language='assembly';finalization_policy='disabled';original_Finalizer_initializer_and_getQueue_executed=$true;original_queue_constructors_executed=$true;cold_parallel_Java_calls=1024;workers=8;canonical_queue_and_static_fields_checked=$true;quiescent_GC_preserves_rooted_queue=$true;enabled_finalizers_implemented=$false;automatic_GC=$false;System_boot_phases_completed=$false;game_started=$false;world_created=$false;full_game_ready=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-finalization-test.txt',$root);Write-Output $json
exit 0
