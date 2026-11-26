param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/access-context-tests/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-access-context-test.txt',$root)
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -d (Join-Path $root classes) java/subset/dev/boom/security/AccessDomain.java
if($LASTEXITCODE -ne 0){throw 'Access domain metadata fixture javac failed'}
$arguments=@('compile-program')
foreach($name in @('AccessDomain','AccessDomain$A','AccessDomain$B')){$arguments+=@('--class-file',(Join-Path $root "classes/dev/boom/security/$name.class"))}
$arguments+=@('--entry-class','java/security/AccessController','--method','getStackAccessControlContext','--descriptor','()Ljava/security/AccessControlContext;','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--output',(Join-Path $root program),'--assemble')
& $Boom @arguments > (Join-Path $root compile.json) 2> (Join-Path $root compile.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root compile.err) -Tail 12;throw 'Native access context compilation failed'}
$p=Get-Content (Join-Path $root program/program.json) -Raw|ConvertFrom-Json
if($p.schema -ne 55 -or $p.full_game_ready -or $p.access_context.abi -ne 1 -or $p.access_context.automatic_gc -or -not $p.access_context.application_domains_require_explicit_binding){throw 'Access context capability scope differs'}
& D:/Dev/Python312/python.exe scripts/verify-access-context.py (Join-Path $root program/program.json) > (Join-Path $root source-contract.json)
if($LASTEXITCODE -ne 0){throw 'Independent access context metadata verification failed'}
function TypeId([string]$name){for($i=0;$i -lt $p.mirror_types.Count;$i++){if($p.mirror_types[$i].key.name -eq $name){return [uint32]$i}};throw "Missing metadata type $name"}
$a=TypeId 'dev/boom/security/AccessDomain$A';$b=TypeId 'dev/boom/security/AccessDomain$B'
$pdRow=-1;for($i=0;$i -lt $p.runtime_type_bindings.Count;$i++){if($p.runtime_type_bindings[$i].tag -eq 'OFFSET boom_access_pd_layout'){$pdRow=$i;break}}
if($pdRow -lt 0){throw 'Missing VM PD view type binding'}
Add-Type -Path tests/host/AccessContextProbe.cs
[BoomAccessContextProbe]::Run($p.compilation.dll,$a,$b,[uint32]$p.access_context.thread,$pdRow)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Access context compiler changed during tests'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';original_AccessController_ACC_and_Thread_initializers_executed=$true;native_entry_executed=$true;parallel_capture_workers=8;parallel_capture_calls=512;VM_caller_sensitive_and_ignored_frame_class_identity_checked=$true;original_Reflection_initializer_and_Java_callsite_executed=$false;VM_stack_domain_order_and_privileged_stop_checked=$true;VM_frames_are_explicit_fixtures=$true;VM_PD_and_Thread_storage_are_preconstructor_fixtures=$true;application_domain_binding_immutable_and_rooted=$true;unbound_domain_and_active_frame_binding_rejected=$true;inherited_ACC_identity_null_and_type_checks_passed=$true;native_escape_heap_validation_passed=$true;quiescent_GC_domain_roots_verified=$true;original_Java_getContext_optimize_executed=$false;general_Thread_constructor_complete=$false;automatic_gc=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 4
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText('.boom/latest-access-context-test.txt',$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
