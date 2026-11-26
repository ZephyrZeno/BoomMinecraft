param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/class-loader-tests/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-class-loader-test.txt',$root)
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
$javac=Join-Path (Split-Path $inputs.java.executable) javac.exe
& $javac --release 21 -g -proc:none -d (Join-Path $root classes) java/subset/dev/boom/loading/LoaderIdentity.java java/reference/ClassLoaderReference.java
if($LASTEXITCODE -ne 0){throw 'Loader metadata/reference fixture javac failed'}
& $inputs.java.executable --add-opens=java.base/java.lang=ALL-UNNAMED -cp (Join-Path $root classes) ClassLoaderReference > (Join-Path $root reference.txt)
if($LASTEXITCODE -ne 0){throw 'Locked JVM loader identity oracle failed'}
$reference=Get-Content (Join-Path $root reference.txt)
if(($reference -join "`n") -ne "int=bootstrap`n[[I=bootstrap`njava.lang.Object=bootstrap`n[Ljava.lang.String;=bootstrap`ndev.boom.loading.LoaderIdentity`$A=application`ndev.boom.loading.LoaderIdentity`$B=application`n[[Ldev.boom.loading.LoaderIdentity`$A;=application"){throw 'Locked JVM component loader expectations differ'}
$arguments=@('compile-program')
foreach($name in @('LoaderIdentity','LoaderIdentity$A','LoaderIdentity$B')){$arguments+=@('--class-file',(Join-Path $root "classes/dev/boom/loading/$name.class"))}
$arguments+=@('--entry-class','java/lang/Class$$BoomJdk$000f','--method','getClassLoader0','--descriptor','(Ljava/lang/Class;)Ljava/lang/ClassLoader;','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--output',(Join-Path $root program),'--assemble')
& $Boom @arguments > (Join-Path $root compile.json) 2> (Join-Path $root compile.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root compile.err) -Tail 12;throw 'Native Class getter compilation failed'}
& $Boom inspect-jdk-bridges --lock $MetadataLock --jdk-base $JdkBase --bridge-id 14 --bridge-id 15 --output (Join-Path $root bridges) > (Join-Path $root bridges.json)
if($LASTEXITCODE -ne 0){throw 'Original Class getter source inspection failed'}
& D:/Dev/Python312/python.exe scripts/verify-class-loaders.py (Join-Path $root program/program.json) (Join-Path $root bridges/inspection.json) > (Join-Path $root source-contract.json)
if($LASTEXITCODE -ne 0){throw 'Independent loader source verification failed'}
$p=Get-Content (Join-Path $root program/program.json) -Raw|ConvertFrom-Json
$appType=-1;for($i=0;$i -lt $p.mirror_types.Count;$i++){if($p.mirror_types[$i].key.name -eq 'dev/boom/loading/LoaderIdentity$A'){$appType=$i;break}}
$loaderRow=-1;for($i=0;$i -lt $p.runtime_type_bindings.Count;$i++){if($p.runtime_type_bindings[$i].tag -eq 'OFFSET boom_loader_vm_layout'){$loaderRow=$i;break}}
if($appType -lt 0 -or $loaderRow -lt 0){throw 'Missing loader metadata binding'}
Add-Type -Path tests/host/ClassLoaderProbe.cs
[BoomClassLoaderProbe]::Run($p.compilation.dll,[uint32]$appType,[uint32]$p.class_loaders.type_loader_ids[$appType],$loaderRow,[uint32[]]$p.class_loaders.type_loader_ids)
& $inputs.java.executable --add-opens=java.base/java.lang=ALL-UNNAMED -cp (Join-Path $root classes) ClassLoaderReference registration > (Join-Path $root registration-reference.txt)
if($LASTEXITCODE -ne 0 -or (Get-Content (Join-Path $root registration-reference.txt)|Select-Object -Last 1) -ne 'registration_calls=256;null_name=true'){throw 'Locked JVM ClassLoader registration oracle failed'}
& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class java/lang/ClassLoader --method checkName --descriptor '(Ljava/lang/String;)Z' --output (Join-Path $root registration) --assemble > (Join-Path $root registration.json) 2> (Join-Path $root registration.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root registration.err) -Tail 12;throw 'Original ClassLoader initializer compilation failed'}
& D:/Dev/Python312/python.exe scripts/verify-class-loaders.py (Join-Path $root registration/program.json) (Join-Path $root bridges/inspection.json) registration > (Join-Path $root registration-contract.json)
if($LASTEXITCODE -ne 0){throw 'Independent ClassLoader native registration verification failed'}
$registration=Get-Content (Join-Path $root registration/program.json) -Raw|ConvertFrom-Json
[BoomClassLoaderProbe]::RunRegistration($registration.compilation.dll)
& D:/Dev/Python312/python.exe scripts/make-platform-private-fixtures.py (Join-Path $root forged)
if($LASTEXITCODE -ne 0){throw 'Private native fixture generation failed'}
& $Boom compile-program --class-file (Join-Path $root forged/PrivateLoaderRegister.class) --entry-class dev/boom/platform/PrivateLoaderRegister --method run --descriptor '()V' --metadata-lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root rejected) > (Join-Path $root rejected.json) 2> (Join-Path $root rejected.err)
if($LASTEXITCODE -eq 0 -or (Get-Content (Join-Path $root rejected.err) -Raw) -notmatch 'ClassLoader.registerNatives is private'){throw 'Application private ClassLoader native call was not rejected'}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Class loader compiler changed during tests'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';original_getClassLoader0_Java_Code_executed=$true;original_public_getClassLoader_Code_preserved=$true;original_public_getClassLoader_executed=$false;JVM_reference_cases=7;component_loader_metadata_cases=$p.mirror_types.Count;parallel_source_getter_workers=8;parallel_source_getter_calls=4096;loader_identity_immutable_and_rooted=$true;unbound_application_loader_rejected=$true;foreign_heap_wrong_type_active_execution_binding_rejected=$true;pending_context_preserved=$true;quiescent_GC_loader_roots_verified=$true;ClassLoader_storage_is_preconstructor_VM_fixture=$true;original_ClassLoader_initializer_executed=$false;original_ClassLoader_constructor_executed=$false;System_boot_phases_completed=$false;automatic_gc=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;run_directory=$root}
$report.original_ClassLoader_initializer_executed=$true
$report['compiled_images']=2
$report['original_ClassLoader_checkName_null_executed']=$true
$report['ClassLoader_initializer_parallel_workers']=8
$report['ClassLoader_initializer_source_calls']=512
$report['ClassLoader_idempotent_registration_JVM_and_ASM_calls']=256
$report['ClassLoader_registered_members']=1
$report['retrieveDirectives_implemented']=$false
$report['unimplemented_directives_raise_UnsatisfiedLinkError']=$true
$report['application_private_registration_call_rejected']=$true
$json=$report|ConvertTo-Json -Depth 4
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText('.boom/latest-class-loader-test.txt',$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
exit 0
