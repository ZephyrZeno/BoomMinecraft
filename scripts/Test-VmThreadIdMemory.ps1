param([Parameter(Mandatory=$true)][string]$Runtime)
$ErrorActionPreference='Stop';$dll=Join-Path (Resolve-Path -LiteralPath $Runtime).Path 'boom-runtime.dll'
$root=Join-Path (Get-Location) ('.boom/vm-thread-id-memory-tests/'+[guid]::NewGuid().ToString('N'));[IO.Directory]::CreateDirectory($root)|Out-Null
$sha=(Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant()
Add-Type -Path (Join-Path $PSScriptRoot '../tests/host/VmThreadIdMemoryProbe.cs')
$v=[BoomVmThreadIdMemoryProbe]::Run($dll)
if((Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sha){throw 'VM counter runtime changed during execution'}
$result=[ordered]@{passed=$true;scope='assembly_VM_counter_domain_and_registry_destruction_lifetime_only';runtime=$dll;runtime_sha256=$sha;workers=$v[0];unique_parallel_increments=$v[1];error_checks=$v[2];destroyed_address_rejections=$v[3];arbitrary_off_heap=$false;original_Unsafe_and_ThreadIdentifiers_executed=$false;full_VM_bootstrap=$false;game_started=$false;world_created=$false;run_directory=$root}
$json=$result|ConvertTo-Json;[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
