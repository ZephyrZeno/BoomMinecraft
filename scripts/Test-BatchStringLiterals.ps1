param([Parameter(Mandatory=$true)][string]$Batch,[string]$Runtime='.boom/assembly-runtime-v87-final',[string]$Output='')
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=if($Output){[IO.Path]::GetFullPath($Output)}else{Join-Path $project ('.boom/batch-string-probes/'+[guid]::NewGuid().ToString('N'))}
[IO.Directory]::CreateDirectory($root)|Out-Null
$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
& D:/Dev/Python312/python.exe (Join-Path $PSScriptRoot 'prepare-batch-string-probe.py') $Batch $root > "$root/prepare.json"
if($LASTEXITCODE -ne 0){throw 'Source-backed literal probe preparation failed'}
$probe=Get-Content "$root/probe.json" -Raw|ConvertFrom-Json
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content (Join-Path $installation 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
$bin=Join-Path $installation "VC/Tools/MSVC/$version/bin/Hostx64/x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10
$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path (Join-Path $_.FullName 'um/x64/synchronization.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$object=Join-Path $root 'original-string-methods.obj';$dll=Join-Path $root 'batch-string-literals.dll'
& (Join-Path $bin 'ml64.exe') /nologo /c "/Fo$object" (Join-Path $root 'original-string-methods.asm')
if($LASTEXITCODE -ne 0){throw 'Original String method assembly failed'}
$exports=@('boom_java_string_literal','boom_java_string_literals_bind_heap','boom_java_string_literal_pool','boom_java_string_literal_roots','boom_java_string_literal_root_count',$probe.methods.value.symbol,$probe.methods.isEmpty.symbol)
$exports+=Get-Content "$root/aliases.tsv"|ForEach-Object{($_ -split "`t")[0]}
if($probe.runtime_metadata){
    $exports+=@('boom_runtime_type_map','boom_batch_type_descriptors','boom_batch_field_records')
    $exports+=@($probe.runtime_metadata.thunk_ids|ForEach-Object{'boom_field_map'+$_})
}
if($probe.boxed_types){
    foreach($property in $probe.boxed_types.PSObject.Properties){$exports+=@($property.Value.constructor.symbol,$property.Value.getter.symbol)}
}
# Response file contains fixed flags and literal local paths; no shell command text.
$lines=@('/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT','/BREPRO',('/OUT:"'+$dll+'"'),('"'+$object+'"'))
$lines+=@($probe.objects|ForEach-Object{'"'+$_+'"'})
$lines+=('"'+(Join-Path $runtimePath 'boom-runtime.lib')+'"'),('"'+(Join-Path $sdk.FullName 'um/x64/synchronization.lib')+'"')
$lines+=@($exports|ForEach-Object{'/EXPORT:'+$_})
[IO.File]::WriteAllLines("$root/link.rsp",[string[]]$lines,[Text.UTF8Encoding]::new($false))
& (Join-Path $bin 'link.exe') "@$root/link.rsp" > "$root/link.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/link.log" -Tail 20;throw 'Batch String module link failed'}
$java='D:/Dev/Java/jdk-21/bin'
& "$java/javac.exe" --release 21 -proc:none -encoding UTF-8 -d "$root/reference" (Join-Path $project 'java/reference/JavaStringLiteralReference.java')
if($LASTEXITCODE -ne 0){throw 'String oracle compilation failed'}
& "$java/java.exe" -Xmx512m --add-opens java.base/java.lang=ALL-UNNAMED -cp "$root/reference" JavaStringLiteralReference "$root/input-utf16.txt" > "$root/oracle.tsv" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){throw 'Actual source literal JVM oracle failed'}
Add-Type -Path (Join-Path $project 'tests/host/JavaStringLiteralProbe.cs')
$counts=[BoomJavaStringLiteralProbe]::RunGenerated((Join-Path $runtimePath 'boom-runtime.dll'),$dll,"$root/oracle.tsv","$root/aliases.tsv",$probe.methods.value.symbol,$probe.methods.isEmpty.symbol)
$metadataResult=$null
if($probe.runtime_metadata){
    Add-Type -Path (Join-Path $project 'tests/host/BatchMetadataProbe.cs')
    $nativeMetadata=[BoomBatchMetadataProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),$dll,$root,$probe.runtime_metadata.type_capacity)
    $metadataResult=[ordered]@{source_runtime_rows=$nativeMetadata[0];source_field_offsets=$nativeMetadata[1];field_thunk_calls=$nativeMetadata[2];guest_allocated_bytes=$nativeMetadata[3];workers=$nativeMetadata[4];lookup_guest_allocations=0;quiescent_rooted_and_unrooted_collection=$true;Java_constructors_executed=$false}
}
$result=[ordered]@{passed=$true;scope='batch_source_String_literals_and_two_original_Java_method_bodies';runtime_language='assembly';batch=$probe.batch;canonical_cases=$counts[0];native_literal_calls=$counts[1];original_String_Java_body_calls=$counts[2];alias_calls=$counts[3];guest_allocated_bytes=$counts[4];workers=$counts[5];methods=$probe.methods;source_layout=$probe.source_layout;quiescent_explicit_gc=$true;general_String_intern=$false;String_clinit_executed=$false;full_class_initialization_wrappers_executed=$false;automatic_gc=$false;game_started=$false;world_created=$false;full_game_ready=$false;run_directory=$root}
$result['runtime_metadata_execution']=$metadataResult
if($probe.boxed_types){
    & "$java/javac.exe" --release 21 -proc:none -encoding UTF-8 -d "$root/reference" (Join-Path $project 'java/reference/BoxedValueReference.java')
    if($LASTEXITCODE -ne 0){throw 'Boxed value oracle compilation failed'}
    & "$java/java.exe" -Xmx128m -cp "$root/reference" BoxedValueReference "$root/boxed-cases.tsv" > "$root/boxed-oracle.tsv" 2> "$root/boxed-oracle.err"
    if($LASTEXITCODE -ne 0){throw 'Boxed value JVM oracle failed'}
    Add-Type -Path (Join-Path $project 'tests/host/BoxedBodyProbe.cs')
    $boxedCounts=[BoomBoxedBodyProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),$dll,$root)
    $result['original_boxed_body_execution']=[ordered]@{source_types=$boxedCounts[0];JVM_cases=$boxedCounts[1];Java_constructor_and_accessor_calls=$boxedCounts[2];workers=$boxedCounts[3];class_initialization_executed=$false;source_methods=$probe.boxed_types}
}
$json=$result|ConvertTo-Json -Depth 9
[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $project '.boom/latest-batch-string-test.txt'),$root,[Text.UTF8Encoding]::new($false))
Write-Output $json
