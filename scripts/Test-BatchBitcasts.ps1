param([Parameter(Mandatory=$true)][string]$Directory,[string]$Runtime='.boom/assembly-runtime-v104')
$ErrorActionPreference='Stop';$dir=(Resolve-Path -LiteralPath $Directory).Path;$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$closure=Get-Content (Join-Path $dir 'closure.json') -Raw|ConvertFrom-Json;$proof=Get-Content (Join-Path $dir 'selection-verification.json') -Raw|ConvertFrom-Json
if(-not $proof.verified -or -not $proof.diagnostic_only -or -not $closure.selected_bitcast_natives){throw 'Bitcast probe requires an independently checked source native image'}
$summary=Get-Content (Join-Path $closure.batch 'summary.json') -Raw|ConvertFrom-Json;$m=$summary.bitcasts
$root=Join-Path (Split-Path $PSScriptRoot -Parent) ('.boom/normal-bitcast-probes/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
& D:/Dev/Python312/python.exe -c 'import json,sys,zipfile;from pathlib import Path;s=json.loads(Path(sys.argv[1]).read_text());m=s["bitcasts"];z=zipfile.ZipFile(m["index"]["path"]);a=list(map(json.loads,z.read("methods.jsonl").splitlines()));c=zipfile.ZipFile(s["class_state"]["index"]["path"]);states={x["class_id"]:x for x in map(json.loads,c.read("classes.jsonl").splitlines()) if x["class_id"] in m["source_class_ids"]};print(json.dumps(dict(names=["boom_m"+str(x["method"]) for x in a],classes=m["source_class_ids"],type_fields=[next(f["index"] for f in states[i]["fields"] if f["name"]=="TYPE") for i in m["source_class_ids"]])))' (Join-Path $closure.batch 'summary.json') > "$root/source.json"
if($LASTEXITCODE -ne 0){throw 'Bitcast source address inspection failed'}
$source=Get-Content "$root/source.json" -Raw|ConvertFrom-Json
Add-Type -Path tests/host/NormalBitcastsProbe.cs;$cases=[BoomNormalBitcastsProbe]::WriteCases((Join-Path $root 'cases.tsv'))
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -proc:none -d "$root/reference" java/reference/NormalBitcastsReference.java > "$root/javac.log" 2>&1
if($LASTEXITCODE -ne 0){throw 'Bitcast JVM oracle compile failed'}
& D:/Dev/Java/jdk-21/bin/java.exe -cp "$root/reference" NormalBitcastsReference "$root/cases.tsv" > "$root/oracle.tsv" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){throw 'Bitcast JVM oracle failed'}
$v=[BoomNormalBitcastsProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),(Join-Path $dir 'diagnostic-image.dll'),(Join-Path $root 'oracle.tsv'),[string[]]$source.names,[int[]]$source.classes,[int[]]$source.type_fields)
if($v[2] -ne $cases){throw 'Bitcast oracle coverage differs'}
$result=[ordered]@{passed=$true;fixture_only=$false;diagnostic_image=$true;source_closure_complete=$false;scope='original_Float_Double_initializers_four_raw_native_entries_managed_slot_bit_patterns_and_width';
batch=$closure.batch;source_image=$dir;source_numeric_classes_initialized=2;native_methods=4;source_native_declarations=$m.source_native_declarations;cold_init_workers=$v[0];parallel_calls=$v[1];bit_patterns=$v[2];JVM_strict_roundtrip_cases=$v[3];JVM_signaling_NaN_copy_variations=$v[4];sequential_native_calls=$v[5];error_checks=$v[6];
signaling_and_quiet_NaN_payloads_preserved_by_ASM=$true;canonical_Java_wrappers_executed_by_probe=$false;numeric_conversion=$false;automatic_gc=$false;System_boot_phases_completed=$false;game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$json=$result|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
