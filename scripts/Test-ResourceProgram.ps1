param([string]$Boom='target\release\boom.exe',[string]$MetadataLock='.boom\locks\server.json',[string]$JdkBase='',[string]$JdkModules='')
$ErrorActionPreference='Stop'
$compilerSha=(Get-FileHash $Boom).Hash.ToLowerInvariant()
if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content .boom/latest-server-jdk-base.txt -Raw).Trim()) 'jdk-base.json'}
if(-not $JdkModules){$JdkModules=Join-Path ((Get-Content .boom/latest-server-jdk-modules.txt -Raw).Trim()) 'jdk-modules.json'}
$root=Join-Path (Get-Location) ('.boom/resource-program-tests/'+[guid]::NewGuid().ToString('N'))
$classes=Join-Path $root 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$inputs=Get-Content $MetadataLock -Raw|ConvertFrom-Json
& (Join-Path (Split-Path -Parent $inputs.java.executable) 'javac.exe') --release 21 -proc:none -encoding UTF-8 -d $classes java/subset/dev/boom/resources/ResourceEntry.java java/subset/dev/boom/subset/ClassNumericOracle.java
if($LASTEXITCODE -ne 0){throw 'Resource reference javac failed'}
function Put([IO.Compression.ZipArchive]$archive,[string]$name,[byte[]]$bytes){$entry=$archive.CreateEntry($name,[IO.Compression.CompressionLevel]::Optimal);$stream=$entry.Open();try{$stream.Write($bytes,0,$bytes.Length)}finally{$stream.Dispose()}}
$first=Join-Path $root 'first.jar';$second=Join-Path $root 'second.jar'
$stream=[IO.File]::Create($first);$zip=[IO.Compression.ZipArchive]::new($stream,[IO.Compression.ZipArchiveMode]::Create,$false,[Text.UTF8Encoding]::new($false))
try{
    foreach($file in Get-ChildItem $classes -Recurse -Filter '*.class'){Put $zip ([IO.Path]::GetRelativePath($classes,$file.FullName).Replace('\','/')) ([IO.File]::ReadAllBytes($file.FullName))}
    $values=[ordered]@{'META-INF/MANIFEST.MF'="Manifest-Version: 1.0`r`nMulti-Release: true`r`n`r`n";'dev/boom/resources/local.txt'="local 中文`n";'shared.txt'='first';'empty.bin'='';'empty-dir/'='';'unicode/😀.txt'='supplementary';'unicode/.txt'='private-bmp';'release.txt'='base';'META-INF/versions/9/release.txt'='nine';'META-INF/versions/17/release.txt'='seventeen';'META-INF/versions/21/release.txt'='twenty-one';'META-INF/versions/22/release.txt'='future'}
    foreach($key in $values.Keys){Put $zip $key ([Text.Encoding]::UTF8.GetBytes($values[$key]))}
}finally{$zip.Dispose();$stream.Dispose()}
$stream=[IO.File]::Create($second);$zip=[IO.Compression.ZipArchive]::new($stream,[IO.Compression.ZipArchiveMode]::Create)
try{Put $zip 'shared.txt' ([Text.Encoding]::UTF8.GetBytes('second'))}finally{$zip.Dispose();$stream.Dispose()}
& scripts/Build-AssemblyRuntime.ps1 -Output $root
& scripts/Build-FpProbe.ps1 -Output $root
Add-Type -Path tests/host/NumericProbe.cs
Add-Type -Path tests/host/ResourceProbe.cs
$files=@(Get-ChildItem (Join-Path $classes 'dev/boom/resources') -Filter '*.class')
function Arguments([string]$out,[bool]$modules,[bool]$resources){
    $a=@('compile-program','--entry-class','dev/boom/resources/ResourceEntry','--method','run','--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase,'--output',$out,'--assemble')
    if($modules){$a+=@('--jdk-modules',$JdkModules)}
    if($resources){$a+=@('--resource-jar',$first,'--resource-jar',$second)}
    foreach($file in $files){$a+=@('--class-file',$file.FullName)}
    return $a
}
$destination=Join-Path $root 'program';$arguments=Arguments $destination $true $true
& $Boom @arguments > (Join-Path $root 'compile-output.json')
if($LASTEXITCODE -ne 0){throw "Class resource compilation failed: $root"}
$p=Get-Content (Join-Path $destination 'program.json') -Raw|ConvertFrom-Json
if($p.schema -ne 19 -or -not $p.resources -or $p.resources.pack.abi -ne 1 -or $p.resources.anchors.Count -ne $p.mirror_types.Count){throw 'Resource program metadata contract mismatch'}
if((Get-FileHash $p.resources.file).Hash.ToLowerInvariant() -ne $p.resources.pack.file.sha256){throw 'Resource sidecar changed'}
Write-Output 'Compiled frozen class resource entry.'
$cases=[Collections.Generic.List[object]]::new()
$names=@(0..16|ForEach-Object{$_.ToString('x')})+@('ffffffff','80000000','7fffffff')
foreach($n in $names){foreach($a in @('0','1','2','3','4','5','6','ffffffff')){$cases.Add(@{values=@($n,$a,'0')})}}
foreach($n in @('0','1','2','3','7','e')){foreach($op in @('1','2')){$cases.Add(@{values=@($n,'0',$op)})}}
foreach($a in @('1','2','3','4')){foreach($op in @('1','2')){$cases.Add(@{values=@('a',$a,$op)})}}
$classpath=@($first,$second)+@($inputs.classpath|ForEach-Object{$id=$_;(@($inputs.files|Where-Object id -eq $id)[0]).path})
$info=[Diagnostics.ProcessStartInfo]::new();$info.FileName=$inputs.java.executable;$info.UseShellExecute=$false;$info.CreateNoWindow=$true;$info.RedirectStandardInput=$true;$info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
foreach($arg in @('-cp',($classpath -join ';'),'dev.boom.subset.ClassNumericOracle')){$info.ArgumentList.Add($arg)}
foreach($key in @('JAVA_TOOL_OPTIONS','_JAVA_OPTIONS','JDK_JAVA_OPTIONS','CLASSPATH')){$info.Environment.Remove($key)|Out-Null}
$oracle=[Diagnostics.Process]::new();$oracle.StartInfo=$info
try{
    if(-not $oracle.Start()){throw 'Resource JVM oracle failed'};$stdout=$oracle.StandardOutput.ReadToEndAsync();$stderr=$oracle.StandardError.ReadToEndAsync()
    $lines=@($cases|ForEach-Object{'dev.boom.resources.ResourceEntry run (III)I '+($_.values -join ' ')})
    if(-not $oracle.StandardInput.WriteAsync(($lines -join "`n")+"`n").Wait(15000)){throw 'Resource oracle input stalled'};$oracle.StandardInput.Close()
    if(-not $oracle.WaitForExit(30000)){throw 'Resource reference timed out'};if($oracle.ExitCode -ne 0){throw $stderr.GetAwaiter().GetResult()}
    $expected=@($stdout.GetAwaiter().GetResult().Split("`n",[StringSplitOptions]::RemoveEmptyEntries)|ForEach-Object{$_.Trim()})
}finally{if(-not $oracle.HasExited){$oracle.Kill($true);$oracle.WaitForExit()};$oracle.Dispose()}
if($expected.Count -ne $cases.Count){throw 'Resource reference count mismatch'}
[string[]]$values=@($cases|ForEach-Object{$_.values -join ' '})
$actual=[BoomNumericProbe]::Run($p.compilation.dll,(Join-Path $root 'fpstate.dll'),$values,'I',$true)
$failures=[Collections.Generic.List[object]]::new()
for($i=0;$i -lt $cases.Count;$i++){if($actual[$i] -ne $expected[$i]){$failures.Add(@{case=$cases[$i];expected=$expected[$i];actual=$actual[$i]})}}
if($failures.Count){$failures|ConvertTo-Json -Depth 8|Set-Content (Join-Path $root 'failures.json');throw "Resource mismatches: $($failures.Count), $root"}
Write-Output 'Class resource JVM/native differential checks passed.'
$gameHash=[Convert]::ToUInt32($expected[0].Substring(2),16)
[BoomResourceProbe]::Parallel($p.compilation.dll,(Join-Path $root 'boom-runtime.dll'),$gameHash)
[BoomResourceProbe]::Budget($p.compilation.dll)
$copy=Join-Path $root '迁移 资源';[IO.Directory]::CreateDirectory($copy)|Out-Null
$copyDll=Join-Path $copy 'method.dll';$copyPack=Join-Path $copy 'resources.pack'
Copy-Item $p.compilation.dll $copyDll;Copy-Item $p.resources.file $copyPack
$relocated=[BoomNumericProbe]::Run($copyDll,(Join-Path $root 'fpstate.dll'),[string[]]@('0 0 0'),'I',$true)
if($relocated[0] -ne $expected[0]){throw 'Resource sidecar depends on original build directory'}
$row=@(@($p.resources.pack.providers|Where-Object name -eq 'explicit-resource-0')[0].entries|Where-Object name -eq 'dev/boom/resources/local.txt')[0]
$stream=[IO.File]::Open($copyPack,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
try{$stream.Position=$row.offset;$byte=$stream.ReadByte();$stream.Position=$row.offset;$stream.WriteByte($byte -bxor 1)}finally{$stream.Dispose()}
$corrupt=[BoomNumericProbe]::Run($copyDll,(Join-Path $root 'fpstate.dll'),[string[]]@('1 0 0'),'I',$true)
if($corrupt[0] -ne 'e java.lang.VerifyError'){throw 'Changed resource payload bypassed SHA256 check'}
$stream=[IO.File]::Open($copyPack,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
try{$stream.Position=$row.offset;$stream.WriteByte($byte);$stream.Position=24;$saved=$stream.ReadByte();$stream.Position=24;$stream.WriteByte($saved -bxor 1)}finally{$stream.Dispose()}
$corrupt=[BoomNumericProbe]::Run($copyDll,(Join-Path $root 'fpstate.dll'),[string[]]@('0 0 0'),'I',$true)
if($corrupt[0] -ne 'e java.lang.VerifyError'){throw 'Changed resource pack identity was accepted'}
$rejections=2
foreach($mode in @('modules','jars')){
    $out=Join-Path $root ('reject-'+$mode);$a=Arguments $out ($mode -ne 'modules') ($mode -ne 'jars')
    & $Boom @a 2>&1|Out-Null;if($LASTEXITCODE -eq 0 -or (Test-Path $out)){throw 'Missing resource namespace inputs were accepted'};$rejections++
}
if((Get-FileHash $Boom).Hash.ToLowerInvariant() -ne $compilerSha){throw 'Resource compiler changed during test'}
$report=[ordered]@{backend='boom-resources-program-v19-masm-x64';compiler_sha256=$compilerSha;runtime_language='assembly';compiled_entries=1;differential_cases=$cases.Count;native_executions=($cases.Count*2);multicore_records=6147;workers=8;original_minecraft_version_resource=$true;version_resource_java_hash=$gameHash;resource_providers=$p.resources.pack.providers.Count;resource_entries=(@($p.resources.pack.providers|ForEach-Object{$_.entries.Count}|Measure-Object -Sum).Sum);resource_pack_bytes=$p.resources.pack.file.size;relative_packages_arrays_primitives_and_interfaces=$true;named_module_encapsulation=$true;multi_release_and_classpath_order=$true;pinned_jar_url_decoder_behavior=$true;resource_payload_sha256=$true;independent_streams=$true;quiescent_gc_and_oom_recovery=$true;file_handle_counts_stable=$true;relocation_unicode_and_spaces=$true;negative_checks=$rejections;dynamic_resource_loading=$false;automatic_gc=$false;passed=$true;full_game_ready=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 6;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));[IO.File]::WriteAllText('.boom/latest-resource-program.txt',$root,[Text.UTF8Encoding]::new($false));Write-Output $json
exit 0
