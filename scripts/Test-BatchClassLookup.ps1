param([Parameter(Mandatory=$true)][string]$Batch,[Parameter(Mandatory=$true)][string]$Plan,[string]$Runtime='.boom/assembly-runtime-v109-frames-a',[string]$ResumeDirectory)
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$root=if($ResumeDirectory){(Resolve-Path -LiteralPath $ResumeDirectory).Path}else{Join-Path $project ('.boom/class-lookup-probes/'+[guid]::NewGuid().ToString('N'))}
if(-not $root.StartsWith((Join-Path $project '.boom/class-lookup-probes')+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)){throw 'Class lookup fixture must remain inside the project probe directory'}
if(Test-Path -LiteralPath "$root/result.json"){throw 'Completed fixture evidence cannot be overwritten'}
if(-not $ResumeDirectory){
    [IO.Directory]::CreateDirectory((Split-Path $root -Parent))|Out-Null
    & D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'prepare-class-lookup-probe.py') $Batch --plan $Plan --output $root > ($root+'.prepare.log') 2> ($root+'.prepare.err')
    if($LASTEXITCODE -ne 0){Get-Content -LiteralPath ($root+'.prepare.err') -Tail 12;throw 'Class lookup source fixture preparation failed'}
}
$source=Get-Content -LiteralPath "$root/source.json" -Raw|ConvertFrom-Json
if($source.batch -ne (Resolve-Path -LiteralPath $Batch).Path -or $source.plan -ne (Resolve-Path -LiteralPath $Plan).Path){throw 'Resumed class lookup fixture source differs'}
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'prepare-class-lookup-modules.py') --source "$root/source.json" > "$root/modules.prepare.log" 2> "$root/modules.prepare.err"
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/modules.prepare.err" -Tail 10;throw 'Explicit Module fixture preparation failed'}
$summaryHash=(Get-FileHash -LiteralPath (Join-Path $Batch 'summary.json') -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText("$root/profile.json",([ordered]@{source_batch_summary_sha256=$summaryHash;admitted_methods=@();admitted_classes=@()}|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
Add-Type -Path (Join-Path $project 'tests/host/NormalClassLookupProbe.cs')
foreach($stage in @('stop','admitted')){
    $image=Join-Path $root $stage
    $selection=@((Join-Path $PSScriptRoot 'prepare-class-lookup-image.py'),'--source',"$root/source.json",'--output',$image,'--runtime',(Join-Path $runtimePath 'boom-runtime.dll'))
    if($stage -eq 'admitted'){$selection+=@('--profile',"$root/admission.json")}
    if($ResumeDirectory -and (Test-Path -LiteralPath "$image/diagnostic-image.dll")){
        & D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'verify-diagnostic-closure.py') $image --output "$image/selection-verification.json" > "$root/$stage.reverification.log" 2> "$root/$stage.reverification.err"
        if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/$stage.reverification.err" -Tail 14;throw 'Resumed source fixture revalidation failed'}
    }else{
        & D:/Dev/Python312/python.exe @selection > "$root/$stage.selection.log" 2> "$root/$stage.selection.err"
        if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/$stage.selection.err" -Tail 12;throw 'Class lookup source selection failed'}
        & (Join-Path $PSScriptRoot 'Build-DiagnosticClosure.ps1') -Batch $Batch -Plan $Plan -Output $image -Runtime $runtimePath -PreparedSelection > "$root/$stage.build.log" 2>&1
        if(-not $?){Get-Content -LiteralPath "$root/$stage.build.log" -Tail 16;throw 'Class lookup source image build failed'}
    }
    $proof=Get-Content -LiteralPath "$image/selection-verification.json" -Raw|ConvertFrom-Json
    if(-not $proof.verified -or -not $proof.diagnostic_only -or $proof.source_Class_lookup_natives -ne 2){throw 'Class lookup image lacks independent source proof'}
    if($stage -eq 'stop'){
        $v=[BoomNormalClassLookupProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),(Join-Path $image 'diagnostic-image.dll'),"$root/names.tsv",'',"$root/enum-fields.tsv",
            $source.native_for_name,$source.native_bootstrap,$source.Java_entry_symbols[0],$source.Java_entry_symbols[1],$source.Java_entry_symbols[2],$source.enums[0].name,$true)
        $diagnostic=Get-Content -LiteralPath "$image/diagnostic.json" -Raw|ConvertFrom-Json
        $fault=@($diagnostic.rows|Where-Object{$_.id -eq $v[1]})
        if($v[0] -ne 45057 -or $fault.Count -ne 1 -or $fault[0].category -ne 5 -or $fault[0].class_id -ne $source.enums[0].class_id){throw 'Source name lookup did not report the expected unselected initialization'}
        [IO.File]::WriteAllText("$root/execution.json",([ordered]@{diagnostic_only=$true;fault=$fault[0];context_kind=$v[0];record_state=$v[2];game_started=$false}|ConvertTo-Json -Depth 16),[Text.UTF8Encoding]::new($false))
        & D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'update-diagnostic-profile.py') $Batch --execution "$root/execution.json" --admitted "$root/profile.json" --output "$root/admission.json" > "$root/admission.log" 2> "$root/admission.err"
        if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/admission.err" -Tail 12;throw 'Source initialization admission failed'}
    }
}
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -proc:none -encoding UTF-8 -d "$root/reference" (Join-Path $project 'java/reference/NormalClassLookupReference.java') > "$root/javac.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/javac.log" -Tail 8;throw 'Class lookup JVM oracle compile failed'}
& D:/Dev/Java/jdk-21/bin/java.exe -cp "$root/reference" NormalClassLookupReference "$root/oracle-cases.txt" > "$root/oracle.tsv" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){Get-Content -LiteralPath "$root/oracle.err" -Tail 10;throw 'Class lookup JVM oracle failed'}
$image=Join-Path $root 'admitted'
$v=[BoomNormalClassLookupProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),(Join-Path $image 'diagnostic-image.dll'),"$root/names.tsv","$root/oracle.tsv","$root/enum-fields.tsv",
    $source.native_for_name,$source.native_bootstrap,$source.Java_entry_symbols[0],$source.Java_entry_symbols[1],$source.Java_entry_symbols[2],'',$false)
if($v[1] -ne $source.provided_names -or ($v[1]+$v[2]) -ne $source.names -or $v[6] -ne 6 -or $v[8] -ne 4096){throw 'Class lookup execution coverage differs from source cases'}
$result=[ordered]@{passed=$true;scope='source_bootstrap_name_lookup_and_executed_class_initialization_admission';batch=$source.batch;run_directory=$root;source_image=$image;
native_methods=2;cold_Class_workers=$v[0];provided_bootstrap_names=$v[1];unavailable_source_names=$v[2];source_forName_native_calls=$v[3];bootstrap_native_service_calls=$v[4];
original_public_forName_JVM_cases=$v[5];original_enum_name_and_ordinal_cases=$v[6];cold_target_initializer_workers=$v[7];parallel_source_lookups=$v[8];error_checks=$v[9];
executed_initialization_request_verified=$true;class_initialization_admitted_automatically=$true;lookup_false_preserves_cold_state=$true;array_lookup_preserves_component_cold_state=$true;
ClassLoader_initializer_executed=$false;bootstrap_service_test_skips_ClassLoader_wrapper=$true;fixture_String_inputs=$true;custom_loaders=$false;dynamic_array_types=$false;
fixture_bootstrap_Module_objects=$v[10];Module_constructors_executed=$false;module_bootstrap_executed=$false;
Throwable_objects_materialized=$false;automatic_gc=$false;diagnostic_image=$true;source_closure_complete=$false;System_boot_phases_completed=$false;game_started=$false;world_created=$false;full_game_ready=$false}
$json=$result|ConvertTo-Json -Depth 4;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
