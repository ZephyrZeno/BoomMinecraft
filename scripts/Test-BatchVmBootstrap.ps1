param([Parameter(Mandatory=$true)][string]$Directory,[string]$Runtime='.boom/assembly-runtime-v102')
$ErrorActionPreference='Stop';$dir=(Resolve-Path -LiteralPath $Directory).Path;$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$closure=Get-Content (Join-Path $dir 'closure.json') -Raw|ConvertFrom-Json;$proof=Get-Content (Join-Path $dir 'selection-verification.json') -Raw|ConvertFrom-Json;$execution=Get-Content (Join-Path $dir 'execution.json') -Raw|ConvertFrom-Json
if(-not $proof.verified -or -not $proof.diagnostic_only -or -not $execution.completed_requested_entries){throw 'VM probe needs completed, independently checked source initialization'}
$summary=Get-Content (Join-Path $closure.batch 'summary.json') -Raw|ConvertFrom-Json;$m=$summary.vm_registration
$root=Join-Path (Split-Path $PSScriptRoot -Parent) ('.boom/normal-vm-probes/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe -c 'import json,sys,zipfile;from pathlib import Path;s=json.loads(Path(sys.argv[1]).read_text());m=s["vm_registration"];z=zipfile.ZipFile(m["index"]["path"]);methods=list(map(json.loads,z.read("methods.jsonl").splitlines()));states=zipfile.ZipFile(s["class_state"]["index"]["path"]);c=next(x for x in map(json.loads,states.read("classes.jsonl").splitlines()) if x["class_id"]==m["class_id"]);f={x["name"]:x["index"] for x in c["fields"]};print(json.dumps(dict(names=["boom_m"+str(x["method"]) for x in methods],fields=f)))' (Join-Path $closure.batch 'summary.json') > "$root/source.json"
if($LASTEXITCODE -ne 0){throw 'VM probe source address inspection failed'}
$source=Get-Content "$root/source.json" -Raw|ConvertFrom-Json
Add-Type -Path tests/host/NormalVmBootstrapProbe.cs;Add-Type -Path tests/host/VmRegistrationProbe.cs
$runtimeDll=Join-Path $runtimePath 'boom-runtime.dll';$arithmetic=[BoomVmRegistrationProbe]::ArithmeticCases($runtimeDll);if($arithmetic -ne 20126){throw 'VM arithmetic oracle scope differs'}
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -proc:none -d "$root/reference" java/reference/NormalVmTimeReference.java > "$root/javac.log" 2>&1
if($LASTEXITCODE -ne 0){throw 'VM JVM oracle compile failed'}
$before=[BoomVmRegistrationProbe]::NowFileTime()
& D:/Dev/Java/jdk-21/bin/java.exe --add-opens java.base/jdk.internal.misc=ALL-UNNAMED -cp "$root/reference" NormalVmTimeReference > "$root/oracle.tsv" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){throw 'VM JVM oracle failed'}
$after=[BoomVmRegistrationProbe]::NowFileTime();$oracle=[string[]](Get-Content "$root/oracle.tsv");if($oracle.Count -ne 16){throw 'VM JVM oracle cases differ'}
[BoomVmRegistrationProbe]::ReferenceClock($oracle,$before,$after)
$v=[BoomNormalVmBootstrapProbe]::Run($runtimeDll,(Join-Path $dir 'diagnostic-image.dll'),$m.class_id,$source.names[0],$source.names[1],$source.fields.initLevel,$source.fields.lock,$source.fields.directMemory)
$result=[ordered]@{passed=$true;fixture_only=$false;diagnostic_image=$true;source_closure_complete=$false;scope='original_VM_initializer_and_two_native_bindings_runtime_DLL_target_publication_time_arithmetic_and_ABI1_regression';
batch=$closure.batch;source_image=$dir;source_VM_initialized=$true;native_methods=2;source_native_declarations=$m.source_native_declarations;registered_clock_bindings=1;pool_abi=2;target_belongs_to_runtime_DLL=$true;Java_boot_level_changed_by_native=$false;
cold_init_workers=$v[0];parallel_fixture_registration_calls=$v[1];parallel_source_time_calls=$v[2];source_time_offsets=$v[3];error_checks=$v[4];live_objects=$v[5];arithmetic_cases=$arithmetic;JVM_clock_cases=16;legacy_ABI1_checked=$true;
automatic_gc=$false;System_boot_phases_completed=$false;game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
