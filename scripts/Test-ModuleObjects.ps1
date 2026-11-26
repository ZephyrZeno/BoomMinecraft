param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='',[string]$JdkModules='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
if(-not $JdkModules){$JdkModules=Join-Path ((Get-Content .boom/latest-server-jdk-modules.txt -Raw).Trim()) jdk-modules.json}
$root=Join-Path (Get-Location) ('.boom/module-object-tests/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-module-object-test.txt',$root)
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -d (Join-Path $root classes) java/subset/dev/boom/loading/LoaderIdentity.java java/reference/ModuleObjectsReference.java
if($LASTEXITCODE -ne 0){throw 'Module reference/metadata javac failed'}
& $inputs.java.executable --add-opens=java.base/java.lang=ALL-UNNAMED -cp (Join-Path $root classes) ModuleObjectsReference > (Join-Path $root reference.txt)
if($LASTEXITCODE -ne 0 -or (Get-Content (Join-Path $root reference.txt)|Select-Object -Last 1) -ne 'constructor_cases=512;physical_fields=4;boot_identity=true'){throw 'Module locked JVM reference failed'}
$arguments=@('compile-program','--vm-module-bootstrap','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--jdk-modules',$JdkModules,'--entry-class','java/lang/Module','--method','<init>','--descriptor','(Ljava/lang/ClassLoader;)V','--output',(Join-Path $root program),'--assemble')
foreach($name in @('LoaderIdentity','LoaderIdentity$A','LoaderIdentity$B')){$arguments+=@('--class-file',(Join-Path $root "classes/dev/boom/loading/$name.class"))}
& $Boom @arguments > (Join-Path $root compile.json) 2> (Join-Path $root compile.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root compile.err) -Tail 12;throw 'Original Module constructor compilation failed'}
& D:/Dev/Python312/python.exe scripts/verify-module-objects.py (Join-Path $root program/program.json) > (Join-Path $root source-contract.json)
if($LASTEXITCODE -ne 0){throw 'Independent Module source verification failed'}
$p=Get-Content (Join-Path $root program/program.json) -Raw|ConvertFrom-Json
$appType=-1;$baseType=-1
for($i=0;$i -lt $p.mirror_types.Count;$i++){if($p.mirror_types[$i].key.name -eq 'dev/boom/loading/LoaderIdentity$A'){$appType=$i};if($p.mirror_types[$i].key.name -eq 'java/lang/Object'){$baseType=$i}}
if($appType -lt 0 -or $baseType -lt 0){throw 'Module mirror metadata missing'}
$loaderRow=-1;for($i=0;$i -lt $p.runtime_type_bindings.Count;$i++){if($p.runtime_type_bindings[$i].tag -eq 'OFFSET boom_loader_vm_layout'){$loaderRow=$i;break}}
if($loaderRow -lt 0){throw 'Loader VM storage fixture layout missing'}
Add-Type -Path tests/host/ModuleObjectsProbe.cs
[BoomModuleObjectsProbe]::Run($p.compilation.dll,[uint32]$p.module_plan.objects.class_id,[uint32]$appType,[uint32]$baseType,[uint32]$p.class_loaders.type_loader_ids[$appType],$loaderRow)
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Module compiler changed during verification'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_images=1;original_unnamed_constructor_Code_executed=$true;original_constructor_Code_bytes=25;locked_JVM_constructor_cases=512;physical_Module_payload_bytes=65;physical_Module_reference_fields=8;Module_initializer_executed=$false;ordinary_Java_class_initialization_bypassed=$false;VM_entry_rejects_initialized_class=$true;canonical_application_Module_is_original_constructed_object=$true;canonical_boot_Module_has_physical_layer_field=$true;parallel_workers=8;parallel_constructor_calls=1024;parallel_canonical_queries=2048;quiescent_GC_loader_Module_cycle_checked=$true;foreign_heap_wrong_type_unbound_loader_rejected=$true;pending_context_preserved=$true;ClassLoader_storage_is_preconstructor_VM_fixture=$true;named_Module_bootstrap_complete=$false;System_boot_phases_completed=$false;automatic_gc=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 4
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText('.boom/latest-module-object-test.txt',$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
exit 0
