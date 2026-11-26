param([Parameter(Mandatory=$true)][string]$Batch,[Parameter(Mandatory=$true)][string]$Plan,[Parameter(Mandatory=$true)][string[]]$ProviderPack,[string]$Runtime='.boom/assembly-runtime-v109-frames-a')
$ErrorActionPreference='Stop';$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'));$runtimePath=(Resolve-Path -LiteralPath $Runtime).Path
$root=Join-Path $project ('.boom/identity-provider-tests/'+[guid]::NewGuid().ToString('N'));$image=Join-Path $root 'image';[IO.Directory]::CreateDirectory($root)|Out-Null
$arguments=@((Join-Path $PSScriptRoot 'prepare-identity-provider-probe.py'),'--batch',$Batch,'--plan',$Plan,'--runtime',(Join-Path $runtimePath 'boom-runtime.dll'),'--output',$image)
foreach($pack in $ProviderPack){$arguments+=@('--provider',$pack)}
& D:/Dev/Python312/python.exe @arguments > "$root/prepare.log" 2> "$root/prepare.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/prepare.err" -Tail 20;throw 'Identity provider source selection failed'}
& (Join-Path $PSScriptRoot 'Build-DiagnosticClosure.ps1') -Batch $Batch -Plan $Plan -Output $image -Runtime $runtimePath -PreparedSelection > "$root/build.log" 2>&1
if(-not $?){Get-Content "$root/build.log" -Tail 24;throw 'Identity provider image build failed'}
$m=Get-Content "$image/source.json" -Raw|ConvertFrom-Json
Add-Type -Path (Join-Path $project 'tests/host/NormalIdentityProviderProbe.cs')
$v=[BoomNormalIdentityProviderProbe]::Run((Join-Path $runtimePath 'boom-runtime.dll'),(Join-Path $image 'diagnostic-image.dll'),$m.object_id,$m.class_id,$m.system_id,$m.constructor,$m.string_hash,$m.native_symbols.'0',$m.native_symbols.'1',$m.literal.id,[ushort[]]$m.literal.utf16,[int[]]@($m.arrays|ForEach-Object{$_.type_id}),[long[]]@($m.arrays|ForEach-Object{if($null -eq $_.primitive_tag){-1}else{$_.primitive_tag}}),[int[]]@($m.arrays|ForEach-Object{$_.shift}),[int[]]@($m.arrays|ForEach-Object{$_.kind}))
[IO.Directory]::CreateDirectory("$root/reference")|Out-Null
& D:/Dev/Java/jdk-21/bin/javac.exe --release 21 -proc:none -encoding UTF-8 -d "$root/reference" (Join-Path $project 'java/reference/NormalIdentityReference.java') > "$root/javac.log" 2>&1
if($LASTEXITCODE -ne 0){Get-Content "$root/javac.log" -Tail 12;throw 'Identity oracle compile failed'}
& D:/Dev/Java/jdk-21/bin/java.exe -cp "$root/reference" NormalIdentityReference > "$root/oracle.txt" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/oracle.err" -Tail 12;throw 'Identity oracle failed'}
$result=[ordered]@{passed=$true;batch=$m.batch;scope='normal_source_Object_and_System_identity_with_original_Object_ctor_and_String_hash_override';objects=$v[0];observed_distinct_hashes=$v[1];error_checks=$v[2];workers=$v[3];parallel_calls=$v[4];original_Object_constructors=$v[5];fixture_VM_arrays=2;original_String_hashCode_executed=$true;payload_mutation_preserves_identity=$true;nonmoving_heap_abi=1;JVM_oracle='identity relations only; numeric values are VM-specific';Java_codegen_rerun=$false;diagnostic_image=$true;source_closure_complete=$false;automatic_gc=$false;game_started=$false;run_directory=$root}
$json=$result|ConvertTo-Json;[IO.File]::WriteAllText("$root/result.json",$json,[Text.UTF8Encoding]::new($false));Write-Output $json
