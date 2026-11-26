param([string]$Boom='target/release/boom.exe')
$ErrorActionPreference='Stop';$sha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
$root=Join-Path (Get-Location) ('.boom/opaque-constructor-lookups/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
$classes=Join-Path $root classes
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -g -proc:none -d $classes java/subset/dev/boom/sequence/OpaqueCtorLookup.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'Opaque lookup javac failed'}
$base=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) jdk-base.json;$modules=Join-Path ((Get-Content .boom/latest-server-jdk-modules.txt -Raw).Trim()) jdk-modules.json
& $Boom compile-program --vm-class-lookup --class-file "$classes/dev/boom/sequence/OpaqueCtorLookup.class" --entry-class dev/boom/sequence/OpaqueCtorLookup --method run --descriptor '(I)I' --metadata-lock .boom/locks/server.json --jdk-base $base --jdk-modules $modules --output "$root/program" --assemble > "$root/compile.json" 2> "$root/compile.err"
$code=$LASTEXITCODE;$reason=Get-Content "$root/compile.err" -Raw
if($code -eq 0 -or (Test-Path "$root/program/program.json") -or $reason -notmatch 'System Java startup phases 1/2/3 are required'){throw "Opaque lookup frontier changed; inspect its actual scope: $reason"}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $sha){throw 'Opaque lookup compiler changed'}
$r=[ordered]@{compiler_sha256=$sha;inspection_only=$true;compilation_complete=$false;System_startup_guard_preserved=$true;opaque_Constructor_initialization_executed=$false;runtime_readiness_tested=$false;reason=$reason.Trim();game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$json=$r|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-opaque-ctor-inspection.txt',$root);Write-Output $json
exit 0
