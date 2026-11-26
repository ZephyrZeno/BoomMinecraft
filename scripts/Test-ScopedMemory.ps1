param([string]$Boom='target/release/boom.exe',[string]$MetadataLock='.boom/locks/server.json',[string]$JdkBase='')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json}
$root=Join-Path (Get-Location) ('.boom/scoped-memory-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
[IO.File]::WriteAllText('.boom/current-scoped-memory-test.txt',$root)
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path $inputs.java.executable) javac.exe) --release 21 -g -proc:none -d (Join-Path $root classes) java/reference/ScopedMemoryReference.java
if($LASTEXITCODE -ne 0){throw 'Scoped memory JVM oracle javac failed'}
& $inputs.java.executable --add-opens=java.base/jdk.internal.misc=ALL-UNNAMED -cp (Join-Path $root classes) ScopedMemoryReference > (Join-Path $root reference.txt) 2> (Join-Path $root reference.err)
if($LASTEXITCODE -ne 0 -or (Get-Content (Join-Path $root reference.txt)|Select-Object -Last 1) -ne 'singleton_identity=1;bootstrap=1;register_calls=256'){throw 'Scoped memory JVM bootstrap oracle failed'}
& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class jdk/internal/misc/ScopedMemoryAccess --method getScopedMemoryAccess --descriptor '()Ljdk/internal/misc/ScopedMemoryAccess;' --output (Join-Path $root program) --assemble > (Join-Path $root compile.json) 2> (Join-Path $root compile.err)
if($LASTEXITCODE -ne 0){Get-Content (Join-Path $root compile.err) -Tail 16;throw 'Scoped memory bootstrap AOT compilation failed'}
& D:/Dev/Python312/python.exe scripts/verify-scoped-memory.py (Join-Path $root program/program.json) > (Join-Path $root source-contract.json)
if($LASTEXITCODE -ne 0){throw 'Independent scoped memory source verification failed'}
$p=Get-Content (Join-Path $root program/program.json) -Raw|ConvertFrom-Json;$owner=@($p.classes|Where-Object name -eq 'jdk/internal/misc/ScopedMemoryAccess')[0]
Add-Type -Path tests/host/ScopedMemoryProbe.cs
[BoomScopedMemoryProbe]::Run($p.compilation.dll,[uint32]$owner.id,[uint32]@($owner.fields|Where-Object name -eq UNSAFE)[0].index,[uint32]@($owner.fields|Where-Object name -eq theScopedMemoryAccess)[0].index)
& D:/Dev/Python312/python.exe scripts/make-platform-private-fixtures.py (Join-Path $root forged)
if($LASTEXITCODE -ne 0){throw 'Private scoped memory fixture generation failed'}
& $Boom compile-program --class-file (Join-Path $root forged/PrivateScopedRegister.class) --entry-class dev/boom/platform/PrivateScopedRegister --method run --descriptor '()V' --metadata-lock $MetadataLock --jdk-base $JdkBase --output (Join-Path $root rejected) > (Join-Path $root rejected.json) 2> (Join-Path $root rejected.err)
if($LASTEXITCODE -eq 0 -or (Get-Content (Join-Path $root rejected.err) -Raw) -notmatch 'ScopedMemoryAccess.registerNatives is private'){throw 'Application private scoped registration was not rejected'}
& $Boom compile-locked-program --lock $MetadataLock --jdk-base $JdkBase --entry-class jdk/internal/misc/ScopedMemoryAccess --method closeScope0 --descriptor '(Ljdk/internal/foreign/MemorySessionImpl;)Z' --output (Join-Path $root close-rejected) > (Join-Path $root close.json) 2> (Join-Path $root close.err)
if($LASTEXITCODE -eq 0 -or (Get-Content (Join-Path $root close.err) -Raw) -notmatch 'Native method .*closeScope0.*requires its own assembly runtime binding'){throw 'Unimplemented scoped close native was incorrectly accepted'}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Scoped memory compiler changed during tests'}
$report=[ordered]@{compiler_sha256=$sha;runtime_language='assembly';compiled_images=1;original_ScopedMemoryAccess_initializer_constructor_and_getter_executed=$true;original_Unsafe_initializer_and_singleton_used=$true;cold_bootstrap_workers=8;source_singleton_calls=4096;idempotent_registration_JVM_and_ASM_calls=256;registration_allocates_no_guest_objects=$true;private_registration_source_and_native_metadata_gates=$true;pending_Context32_preserved=$true;quiescent_GC_static_roots_and_identity_checked=$true;registered_members=1;closeScope0_implemented=$false;closeScope0_Java_entry_supported=$false;unimplemented_close_target_fails_explicitly=$true;System_boot_phases_completed=$false;automatic_gc=$false;full_game_ready=$false;game_started=$false;world_created=$false;passed=$true;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 4
[IO.File]::WriteAllText((Join-Path $root result.json),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-scoped-memory-test.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
