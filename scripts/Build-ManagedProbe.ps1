param([string]$Output='.boom\native-managed-probe',[string]$Boom='target\release\boom.exe',[switch]$ArrayKernel,[switch]$ObjectKernel,[switch]$ReferenceKernel,[switch]$ProgramKernel,[switch]$StateKernel,[switch]$ObjectProgramKernel,[switch]$StringKernel,[switch]$MirrorKernel,[switch]$ConcatKernel,[switch]$TypeKernel,[string]$MetadataLock='.boom\locks\client.json',[string]$JdkBase='')
$ErrorActionPreference='Stop'
if(([int]$ArrayKernel.IsPresent+[int]$ObjectKernel.IsPresent+[int]$ReferenceKernel.IsPresent+[int]$ProgramKernel.IsPresent+[int]$StateKernel.IsPresent+[int]$ObjectProgramKernel.IsPresent+[int]$StringKernel.IsPresent+[int]$MirrorKernel.IsPresent+[int]$ConcatKernel.IsPresent+[int]$TypeKernel.IsPresent) -gt 1){throw 'Select one fixture family.'}
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$destination=[IO.Path]::GetFullPath($Output)
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $destination
$tools=Get-Content -LiteralPath (Join-Path $projectRoot '.boom\toolchain.json') -Raw|ConvertFrom-Json
$javac=Join-Path (Split-Path -Parent $tools.java) 'javac.exe'
$classes=Join-Path $destination 'classes';[IO.Directory]::CreateDirectory($classes)|Out-Null
$kernel=Join-Path $destination 'kernel'
if($ProgramKernel -or $StateKernel -or $ObjectProgramKernel -or $StringKernel -or $MirrorKernel -or $ConcatKernel -or $TypeKernel){
    $fixtureFolder=if($TypeKernel){'typechecks'}elseif($ConcatKernel){'concat'}elseif($MirrorKernel){'mirrors'}elseif($StringKernel){'strings'}elseif($StateKernel){'state'}elseif($ObjectProgramKernel){'linkobjects'}else{'link'}
    $javaSources=@(Get-ChildItem -LiteralPath (Join-Path $projectRoot "java\subset\dev\boom\$fixtureFolder") -Filter '*.java' -File|ForEach-Object FullName)
    & $javac --release 21 -proc:none -d $classes @javaSources
    if($LASTEXITCODE -ne 0){throw 'Linked fixture javac failed.'}
    $className=if($TypeKernel){'dev/boom/typechecks/TypeEntry'}elseif($ConcatKernel){'dev/boom/concat/ConcatEntry'}elseif($MirrorKernel){'dev/boom/mirrors/ClassEntry'}elseif($StringKernel){'dev/boom/strings/StringEntry'}elseif($StateKernel){'dev/boom/state/StateEntry'}elseif($ObjectProgramKernel){'dev/boom/linkobjects/ObjectEntry'}else{'dev/boom/link/LinkEntry'}
    $methodName=if($TypeKernel){'actualString'}elseif($ConcatKernel){'intHash'}elseif($MirrorKernel){'mirrorMix'}elseif($StringKernel){'hashMix'}elseif($StateKernel){'table'}elseif($ObjectProgramKernel){'pair'}else{'longRoot'}
    $compileArgs=@('compile-program','--entry-class',$className,'--method',$methodName,'--output',$kernel,'--assemble')
    foreach($file in Get-ChildItem -LiteralPath (Join-Path $classes "dev\boom\$fixtureFolder") -Filter '*.class' -File){$compileArgs+=@('--class-file',$file.FullName)}
    if($MirrorKernel -or $TypeKernel){
        if(-not $JdkBase){$JdkBase=Join-Path ((Get-Content -LiteralPath (Join-Path $projectRoot '.boom\latest-jdk-base.txt') -Raw).Trim()) 'jdk-base.json'}
        $compileArgs+=@('--metadata-lock',$MetadataLock,'--jdk-base',$JdkBase)
    }
    & $Boom @compileArgs|Out-Null
    if($LASTEXITCODE -ne 0){throw 'Linked assembly generation failed.'}
}else{
$fixture=if($ReferenceKernel){'ReferenceArrayKernels'}elseif($ObjectKernel){'ObjectKernels'}elseif($ArrayKernel){'ArrayKernels'}else{'NumericKernels'}
& $javac --release 21 -d $classes (Join-Path $projectRoot "java\subset\dev\boom\subset\$fixture.java")
if($LASTEXITCODE -ne 0){throw 'Managed fixture javac failed.'}
$method=if($ReferenceKernel){'cyclicArray'}elseif($ObjectKernel){'intObject'}elseif($ArrayKernel){'arrayCalls'}else{'longLoop'}
& $Boom compile-managed --class-file (Join-Path $classes "dev\boom\subset\$fixture.class") --method $method --output $kernel --assemble|Out-Null
if($LASTEXITCODE -ne 0){throw 'Managed assembly generation failed.'}
}
$vswhere=Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$installation=(& $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath|Select-Object -First 1)
$version=(Get-Content -LiteralPath (Join-Path $installation 'VC\Auxiliary\Build\Microsoft.VCToolsVersion.default.txt') -Raw).Trim()
$bin=Join-Path $installation "VC\Tools\MSVC\$version\bin\Hostx64\x64"
$sdkRoot=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots').KitsRoot10
$sdk=Get-ChildItem -LiteralPath (Join-Path $sdkRoot 'Lib') -Directory|Where-Object{Test-Path -LiteralPath (Join-Path $_.FullName 'um\x64\kernel32.lib')}|Sort-Object Name -Descending|Select-Object -First 1
$object=Join-Path $destination 'managed-main.obj';$executable=Join-Path $destination 'boom-managed-probe.exe'
$assemblerArgs=@('/nologo','/c',"/Fo$object")
if($ArrayKernel){$assemblerArgs+='/DARRAY_KERNEL'}
if($ObjectKernel){$assemblerArgs+='/DOBJECT_KERNEL'}
if($ReferenceKernel){$assemblerArgs+='/DREFERENCE_KERNEL'}
if($ProgramKernel){$assemblerArgs+='/DPROGRAM_KERNEL'}
if($ObjectProgramKernel){$assemblerArgs+='/DOBJECT_PROGRAM_KERNEL'}
$entry='boom_managed_main';$mainSource='managed_main.asm'
if($StringKernel){$assemblerArgs+='/DSTRING_KERNEL';$entry='boom_state_main';$mainSource='state_main.asm'}
if($ConcatKernel){$assemblerArgs+='/DCONCAT_KERNEL';$entry='boom_state_main';$mainSource='state_main.asm'}
if($MirrorKernel -or $TypeKernel){
    $program=Get-Content -LiteralPath (Join-Path $kernel 'program.json') -Raw|ConvertFrom-Json
    $mode=if($TypeKernel){'/DTYPE_KERNEL'}else{'/DMIRROR_KERNEL'}
    $assemblerArgs+=@($mode,"/DMIRROR_ROOT_COUNT=$($program.mirror_types.Count+$program.string_literals.Count)")
    $entry='boom_state_main';$mainSource='state_main.asm'
}
if($StateKernel){
    $program=Get-Content -LiteralPath (Join-Path $kernel 'program.json') -Raw|ConvertFrom-Json
    $table=@($program.classes|Where-Object name -eq 'dev/boom/state/Table')[0]
    $runs=@($table.fields|Where-Object name -eq 'runs')[0]
    $assemblerArgs+=@("/DTABLE_CLASS_ID=$($table.id)","/DTABLE_RUNS_INDEX=$($runs.index)")
    $entry='boom_state_main';$mainSource='state_main.asm'
}
$assemblerArgs+=(Join-Path $projectRoot "native\probe\$mainSource")
& (Join-Path $bin 'ml64.exe') @assemblerArgs
if($LASTEXITCODE -ne 0){throw 'Managed entry assembly failed.'}
$extraObjects=@()
if($ProgramKernel -or $StateKernel -or $ObjectProgramKernel -or $StringKernel -or $MirrorKernel -or $ConcatKernel -or $TypeKernel){$extraObjects+=Join-Path $kernel 'classes-runtime.obj';$extraObjects+=Join-Path $sdk.FullName 'um\x64\synchronization.lib'}
if($StringKernel -or $MirrorKernel -or $ConcatKernel -or $TypeKernel){$extraObjects+=Join-Path $destination 'strings.obj';$extraObjects+=Join-Path $destination 'string_dynamic.obj'}
if($ConcatKernel){$extraObjects+=Join-Path $destination 'concat.obj'}
if($TypeKernel){$extraObjects+=Join-Path $destination 'runtime_types.obj'}
if($MirrorKernel -or $TypeKernel){$extraObjects+=Join-Path $destination 'mirrors.obj';$extraObjects+=Join-Path $destination 'types.obj'}
& (Join-Path $bin 'link.exe') /NOLOGO /SUBSYSTEM:CONSOLE "/ENTRY:$entry" /MACHINE:X64 /DYNAMICBASE /NXCOMPAT "/OUT:$executable" @extraObjects $object (Join-Path $destination 'parallel.obj') (Join-Path $destination 'pool.obj') (Join-Path $destination 'heap.obj') (Join-Path $destination 'arrays.obj') (Join-Path $destination 'objects.obj') (Join-Path $destination 'references.obj') (Join-Path $kernel 'method.obj') (Join-Path $sdk.FullName 'um\x64\kernel32.lib')
if($LASTEXITCODE -ne 0){throw 'Managed bootstrap link failed.'}
$result=& $executable
if($LASTEXITCODE -ne 0){throw 'Integrated assembly bootstrap failed.'}
[IO.File]::WriteAllText((Join-Path $destination 'result.json'),($result -join "`n"),[Text.UTF8Encoding]::new($false));Write-Output $result
& (Join-Path $bin 'dumpbin.exe') /DEPENDENTS $executable|Set-Content -LiteralPath (Join-Path $destination 'dependencies.txt')
