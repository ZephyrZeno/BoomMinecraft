param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/primordial-thread-tests/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
& $Boom compile-locked-program --vm-primordial-thread --lock $MetadataLock --jdk-base $JdkBase --entry-class java/lang/Thread --method '<init>' --descriptor '(Ljava/lang/ThreadGroup;Ljava/lang/String;ILjava/lang/Runnable;JLjava/security/AccessControlContext;)V' --output (Join-Path $root program) --assemble > (Join-Path $root compile.json) 2> (Join-Path $root compile.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root compile.err) -Tail 10;throw 'Primordial constructor compilation failed'}
$p=Get-Content (Join-Path $root program/program.json) -Raw|ConvertFrom-Json
if($p.schema -ne 54 -or $p.full_game_ready -or -not $p.thread_bootstrap.primordial_only -or $p.thread_bootstrap.general_thread_constructor_complete -or $p.compilation.signature.arguments.Count -ne 0 -or $p.thread_bootstrap.guarded_conditionals.Count -ne 8){throw 'Primordial invocation scope differs'}
& D:/Dev/Python312/python.exe scripts/verify-primordial-thread.py (Join-Path $root program/program.json) > (Join-Path $root source-contract.json)
if($LASTEXITCODE -ne 0){throw 'Independent primordial source verification failed'}
function Fields($owner,$names){[int[]]@(foreach($name in $names){[int]@(@($p.object_layouts|Where-Object class_name -eq $owner)[0].layout.fields|Where-Object name -eq $name)[0].offset})}
$thread=@($p.classes|Where-Object name -eq java/lang/Thread)[0]
$t=Fields java/lang/Thread @('holder','tid','name','interruptLock','inheritedAccessControlContext','scopedValueBindings')
$h=Fields 'java/lang/Thread$FieldHolder' @('group','task','stackSize','priority','daemon','threadStatus')
$a=Fields java/security/AccessControlContext @('context','isPrivileged','isAuthorized')
$marker=[uint32]@($thread.fields|Where-Object name -eq NEW_THREAD_BINDINGS)[0].index
Add-Type -Path tests/host/PrimordialThreadProbe.cs
$vm=@($p.classes|Where-Object name -eq jdk/internal/misc/VM)[0]
$levelField=[uint32]@($vm.fields|Where-Object name -eq initLevel)[0].index
[BoomPrimordialThreadProbe]::Run($p.compilation.dll,[uint32]$thread.id,$marker,$t,$h,$a,[uint32]$vm.id,$levelField,$false)
[BoomPrimordialThreadProbe]::Run($p.compilation.dll,[uint32]$thread.id,$marker,$t,$h,$a,[uint32]$vm.id,$levelField,$true)
$ordinary=(& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class java/lang/Thread --method '<init>' --descriptor '()V' --output (Join-Path $root ordinary) --assemble 2>&1|ForEach-Object ToString)-join "`n"
if($LASTEXITCODE -eq 0 -or $ordinary -notmatch 'System Java startup phases 1/2/3 are required'){throw 'Ordinary Thread allocation was incorrectly treated as primordial'}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Primordial compiler changed during verification'}
$sources=[ordered]@{}
foreach($path in @('src/compiler/thread_bootstrap.rs','scripts/Test-PrimordialThread.ps1','scripts/verify-primordial-thread.py','tests/host/PrimordialThreadProbe.cs')){$sources[$path]=(Get-FileHash $path).Hash.ToLowerInvariant()}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_entries=1;original_Thread_attaching_constructor_executed=$true;original_FieldHolder_system_ThreadGroup_and_ACC_constructors_executed=$true;guarded_source_conditionals=8;primordial_ID_1_and_normal_ID_reservation_checked=$true;source_name_interrupt_lock_holder_and_scoped_bindings_checked=$true;explicit_original_bootstrap_ACC_checked=$true;VM_publishes_RUNNABLE_after_constructor=$true;current_thread_identity_and_repeated_entry_rejection_checked=$true;GC_independent_root_graph_checked=$true;general_Thread_constructor_complete=$false;ordinary_allocation_still_rejected_instead_of_specialized=$true;Thread_start_exit_executed=$false;System_boot_phases_completed=$false;automatic_gc=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;sources=$sources;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 5
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText('.boom/latest-primordial-thread-test.txt',$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
exit 0
