param([Parameter(Mandatory=$true)][string]$Catalog,[string]$MetadataLock='.boom/locks/server.json')
$ErrorActionPreference='Stop'
$project=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=Join-Path $project ('.boom/system-class-tests/'+[guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($root)|Out-Null
$catalogPath=(Resolve-Path -LiteralPath $Catalog).Path
$lockPath=(Resolve-Path -LiteralPath $MetadataLock).Path
$inputs=Get-Content -LiteralPath $lockPath -Raw|ConvertFrom-Json
$catalogData=Get-Content -LiteralPath $catalogPath -Raw|ConvertFrom-Json
$rows=[Text.StringBuilder]::new()
foreach($class in $catalogData.classes.PSObject.Properties){
    [void]$rows.Append($class.Value.source_id.Substring(4)).Append("`t").Append($class.Name).Append("`n")
}
[IO.File]::WriteAllText("$root/classes.tsv",$rows.ToString(),[Text.UTF8Encoding]::new($false))
$java=Join-Path $inputs.java.home 'bin/java.exe'
$javac=Join-Path $inputs.java.home 'bin/javac.exe'
& $javac --release 21 -proc:none -encoding UTF-8 -d "$root/reference" (Join-Path $project 'java/reference/SystemClassLoaderReference.java')
if($LASTEXITCODE -ne 0){throw 'System class loader oracle compilation failed'}
& $java -Xmx512m -cp "$root/reference" SystemClassLoaderReference "$root/classes.tsv" 1> "$root/oracle.tsv" 2> "$root/oracle.err"
if($LASTEXITCODE -ne 0){Get-Content "$root/oracle.err" -Tail 15;throw 'System class loader oracle execution failed'}
& D:/Dev/Python312/python.exe (Join-Path $project 'scripts/verify-system-classes.py') $catalogPath --lock $lockPath --oracle "$root/oracle.tsv" --output "$root/result.json"
if($LASTEXITCODE -ne 0){throw 'System class independent verification failed'}
[IO.File]::WriteAllText((Join-Path $project ('.boom/latest-'+$inputs.side+'-system-class-verification.txt')),$root,[Text.UTF8Encoding]::new($false))
