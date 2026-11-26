param([Parameter(Mandatory=$true)][string]$NumericRun,[int]$Count=65539,[switch]$Persistent,[switch]$ArrayKernels,[switch]$ObjectKernels,[switch]$ReferenceArrays,[switch]$LinkedProgram,[switch]$ObjectProgram,[switch]$StringProgram,[switch]$MirrorProgram,[switch]$ConcatProgram,[switch]$TypeChecks,[switch]$InterfaceProgram,[switch]$InheritanceProgram)
$ErrorActionPreference='Stop'
if(([int]$ArrayKernels.IsPresent+[int]$ObjectKernels.IsPresent+[int]$ReferenceArrays.IsPresent+[int]$LinkedProgram.IsPresent+[int]$ObjectProgram.IsPresent+[int]$StringProgram.IsPresent+[int]$MirrorProgram.IsPresent+[int]$ConcatProgram.IsPresent+[int]$TypeChecks.IsPresent+[int]$InterfaceProgram.IsPresent+[int]$InheritanceProgram.IsPresent) -gt 1){throw 'Select one fixture family.'}
if($Count -lt 1024 -or $Count -gt 1000000){throw 'Count must be 1024..1000000.'}
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$numericRoot=(Resolve-Path -LiteralPath $NumericRun).Path
$numericReport=Get-Content -LiteralPath (Join-Path $numericRoot 'result.json') -Raw|ConvertFrom-Json
if(-not $numericReport.passed){throw 'The numeric JVM differential test must pass first.'}
$root=Join-Path $projectRoot ('.boom\numeric-parallel-tests\'+[guid]::NewGuid().ToString('N'))
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
if($Persistent){& (Join-Path $PSScriptRoot 'Build-FpProbe.ps1') -Output $root}
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Diagnostics;
using System.Threading;
using System.Collections.Generic;
public static class BoomManagedParallelProbe {
    [StructLayout(LayoutKind.Sequential)] public struct Context { public uint Kind,PC,Method,Reserved; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context context,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Map(IntPtr entry,IntPtr input,IntPtr output,uint count,uint jobs);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(uint jobs);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint RunPool(IntPtr pool,IntPtr entry,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Destroy(IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapCreate(ulong budget);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int HeapDestroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong HeapCollect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int BindHeap(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint count);
    static void QuiescentGc(IntPtr module,IntPtr heap,HeapCollect collect) {
        uint count=0;IntPtr roots=IntPtr.Zero,address=GetProcAddress(module,"boom_get_static_roots");
        if(address!=IntPtr.Zero)roots=Marshal.GetDelegateForFunctionPointer<Roots>(address)(out count);
        if(count>65536)throw new Exception("Static/literal root count invalid");
        var live=new HashSet<IntPtr>();var pending=new Stack<IntPtr>();
        for(int i=0;i<count;i++)pending.Push(Marshal.ReadIntPtr(roots,i*8));
        while(pending.Count!=0){IntPtr value=pending.Pop();if(value==IntPtr.Zero||!live.Add(value))continue;uint flags=unchecked((uint)Marshal.ReadInt32(value,-24)),refs=unchecked((uint)Marshal.ReadInt32(value,-20));long bytes=Marshal.ReadInt64(value,-16);if((flags&0xfffffffd)!=0xb00b0001||bytes<0||refs>(ulong)bytes/8||refs>1048576||live.Count>1048576)throw new Exception("Invalid static root graph");for(int i=0;i<refs;i++)pending.Push(Marshal.ReadIntPtr(value,i*8));}
        if(collect(heap,roots,count)==ulong.MaxValue||Marshal.ReadInt64(heap,56)!=live.Count||(live.Count==0&&Marshal.ReadInt64(heap,48)!=0))throw new Exception("Quiescent static/literal-root GC failed");
    }
    public sealed class Measurement {public string method;public int jobs,cases;public double median_ms,gc_median_ms,total_median_ms;public bool passed;}
    public static Measurement[] Run(string runtime,string kernelPath,string method,int count,bool persistent,bool useHeap,bool interfaceProgram,bool inheritanceProgram) {
        IntPtr library=IntPtr.Zero,module=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero,pool=IntPtr.Zero,heap=IntPtr.Zero;
        Destroy destroy=null;
        HeapDestroy heapDestroy=null;HeapCollect collect=null;
        try {
            library=LoadLibraryExW(runtime,IntPtr.Zero,0x1100);module=LoadLibraryExW(kernelPath,IntPtr.Zero,0x1100);
            if(library==IntPtr.Zero||module==IntPtr.Zero)throw new Exception("DLL load failed");
            IntPtr symbol=GetProcAddress(module,"boom_entry");
            IntPtr mapSymbol=GetProcAddress(library,"boom_parallel_numeric");
            if(symbol==IntPtr.Zero||mapSymbol==IntPtr.Zero)throw new Exception("Assembly export missing");
            var entry=Marshal.GetDelegateForFunctionPointer<Entry>(symbol);var map=Marshal.GetDelegateForFunctionPointer<Map>(mapSymbol);
            if(useHeap) {
                var make=Marshal.GetDelegateForFunctionPointer<HeapCreate>(GetProcAddress(module,"boom_heap_create"));
                heapDestroy=Marshal.GetDelegateForFunctionPointer<HeapDestroy>(GetProcAddress(module,"boom_heap_destroy"));
                collect=Marshal.GetDelegateForFunctionPointer<HeapCollect>(GetProcAddress(module,"boom_heap_collect"));
                var bind=Marshal.GetDelegateForFunctionPointer<BindHeap>(GetProcAddress(module,"boom_bind_heap"));
                heap=make(64*1024*1024);if(heap==IntPtr.Zero||bind(heap)!=1)throw new Exception("Array heap binding failed");
            }
            Create create=null;RunPool runPool=null;
            if(persistent) {
                create=Marshal.GetDelegateForFunctionPointer<Create>(GetProcAddress(library,"boom_pool_create"));
                runPool=Marshal.GetDelegateForFunctionPointer<RunPool>(GetProcAddress(library,"boom_pool_run"));
                destroy=Marshal.GetDelegateForFunctionPointer<Destroy>(GetProcAddress(library,"boom_pool_destroy"));
                if(create(0)!=IntPtr.Zero||create(65)!=IntPtr.Zero||runPool(IntPtr.Zero,IntPtr.Zero,IntPtr.Zero,IntPtr.Zero,1)!=87||destroy(IntPtr.Zero)!=87)throw new Exception("Invalid pool parameters accepted");
            }
            var values=new long[checked(count*16)];var expected=new long[checked(count*4)];var actual=new long[expected.Length];
            ulong[] floats={0,0x80000000,0x3f800000,0xbf800000,0x7f800000,0xff800000,0x7fc00000,0x7f800001,1,0x7fffff,0x800000,0x7f7fffff};
            ulong[] doubles={0,0x8000000000000000UL,0x3ff0000000000000UL,0xbff0000000000000UL,0x7ff0000000000000UL,0xfff0000000000000UL,0x7ff8000000000000UL,0x7ff0000000000001UL,1,0xfffffffffffffUL,0x10000000000000UL,0x7fefffffffffffffUL};
            var args=new ulong[16];
            for(int i=0;i<count;i++) {
                Array.Clear(args,0,args.Length);
                if(inheritanceProgram) {
                    args[0]=(uint)(i%4);args[1]=unchecked((uint)(i*1664525+1013904223));
                    if(method=="array"||method=="retained") {args[0]=args[1];args[1]=0;}
                    if(method=="arrayFault") {args[0]=(uint)(i%3);args[2]=unchecked((uint)(i%4-1));}
                }
                else if(interfaceProgram) {
                    args[0]=(uint)(i%4);args[1]=unchecked((uint)(i*1664525+1013904223));
                    if(method=="wide") {args[1]=unchecked((ulong)i*0x123456789abcdefUL);args[2]=doubles[i%doubles.Length];}
                    else if(method=="nil") {args[0]=(uint)i;args[1]=0;}
                }
                else if(method=="longLoop"||method=="longRoot") {args[0]=unchecked((ulong)i*0x123456789abcdefUL+0xfedcba9876543210UL);args[1]=256;}
                else if(method=="longDiv") {args[0]=i%13==0?0x8000000000000000UL:unchecked((ulong)i*0x123456789abcdefUL);args[1]=i%17==0?0:unchecked((ulong)-1L);}
                else if(method=="floatMix"||method=="floatRoot") {args[0]=floats[i%floats.Length];args[1]=floats[(i+3)%floats.Length];args[2]=0x3f800001;}
                else if(method=="doubleMix") {args[0]=doubles[i%doubles.Length];args[1]=doubles[(i+3)%doubles.Length];args[2]=0x3ff0000000000001UL;}
                else if(method=="intObject"||method=="intRoot") {args[0]=unchecked((uint)(i*1664525+1013904223));args[1]=unchecked((uint)(i*37));}
                else if(method=="longObject") {args[0]=unchecked((ulong)i*0x123456789abcdefUL);args[1]=32;}
                else if(method=="nullCall") {args[0]=i%37==0?0u:1u;}
                else if(method=="linkedObjects"||method=="arrayObject"||method=="sumArray"||method=="arrayField"||method=="arrayRoot") {args[0]=unchecked((uint)(i%37==0?-1:i%33));args[1]=unchecked((uint)(i*1664525+1013904223));}
                else if(method=="nullElements"||method=="arrayFault") {int n=i%37==0?-1:i%33;args[0]=unchecked((uint)n);args[1]=unchecked((uint)(n<=0||i%7==0?n:i%n));}
                else if(method=="pair"||method=="wide") {args[0]=unchecked((uint)(i*1664525+1013904223));args[1]=unchecked((uint)(i*37));}
                else if(method=="graph") {args[0]=unchecked((uint)(i*1664525+1013904223));args[1]=unchecked((uint)(i%37==0?-1:i%17));}
                else if(method=="arrays") {int n=i%37==0?-1:i%17;args[0]=unchecked((uint)n);args[1]=unchecked((uint)(n<=0||i%7==0?n:i%n));}
                else if(method=="nullField") {args[0]=unchecked((uint)(i%37==0?-1:i));}
                else if(method=="checks"||method=="name"||method=="boxCast") {args[0]=(uint)i;args[1]=unchecked((uint)(i*1664525+1013904223));}
                else if(method=="referenceJoin"||method=="dynamicString") {args[0]=(uint)i;}
                else if(method=="intHash") {args[0]=unchecked((uint)(i*1664525+1013904223));}
                else if(method=="longHash") {args[0]=unchecked((ulong)i*0x123456789abcdefUL);}
                else if(method=="nested") {args[0]=unchecked((uint)(i*1664525+1013904223));args[1]=unchecked((ulong)i*0x123456789abcdefUL);}
                else if(method=="interned") {args[0]=(uint)(i%257);}
                else if(method=="nameHash"||method=="flags"||method=="component"||method=="primitiveRelation") {args[0]=(uint)i;}
                else if(method=="assignable") {args[0]=(uint)i;args[1]=(uint)(i/16);}
                else if(method=="hashMix") {args[0]=unchecked((uint)(i*1664525+1013904223));args[1]=unchecked((uint)(i*37));}
                else if(method=="character") {args[0]=(uint)i;args[1]=unchecked((uint)(i%7==0?-1:i%6));}
                else if(method=="compare") {args[0]=(uint)i;args[1]=(uint)(i*3);}
                else if(method=="array") {int n=i%37==0?-1:i%17;args[0]=unchecked((uint)n);args[1]=unchecked((uint)(n<=0||i%7==0?n:i%n));}
                else if(method=="state") {args[0]=(uint)i;}
                else if(useHeap) {
                    int n=i%37==0?-1:i%33;args[0]=unchecked((uint)n);
                    if(method=="intArray"||method=="arrayCalls")args[1]=unchecked((uint)(i*1664525+1013904223));
                    else if(method=="longArray")args[1]=unchecked((ulong)i*0x123456789abcdefUL);
                    else if(method=="doubleArray")args[1]=doubles[i%doubles.Length];
                    else if(method=="bounds")args[1]=unchecked((uint)(n<=0||i%7==0?n:i%n));
                    else throw new Exception("Unknown array kernel");
                }
                else throw new Exception("Unknown test method");
                for(int a=0;a<16;a++)values[i*16+a]=unchecked((long)args[a]);
                var context=new Context();expected[i*4]=unchecked((long)entry(ref context,args));
                expected[i*4+1]=unchecked((long)((ulong)context.Kind|((ulong)context.PC<<32)));
                expected[i*4+2]=unchecked((long)((ulong)context.Method|((ulong)context.Reserved<<32)));
            }
            if(useHeap)QuiescentGc(module,heap,collect);
            input=Marshal.AllocHGlobal(checked(count*128));output=Marshal.AllocHGlobal(checked(count*32));Marshal.Copy(values,0,input,values.Length);
            if(map(symbol,input,output,(uint)count,0)!=87||map(symbol,input,output,(uint)count,65)!=87)throw new Exception("Invalid worker count accepted");
            if(map(symbol,input,input,(uint)count,4)!=87)throw new Exception("Aliasing buffers accepted");
            if(map(IntPtr.Zero,IntPtr.Zero,IntPtr.Zero,0,4)!=0)throw new Exception("Empty numeric map failed");
            var results=new Measurement[4];int[] budgets={1,2,4,8};
            for(int b=0;b<budgets.Length;b++) {
                if(persistent) {
                    pool=create((uint)budgets[b]);if(pool==IntPtr.Zero)throw new Exception("Pool creation failed");
                    if(runPool(pool,symbol,input,input,(uint)count)!=87)throw new Exception("Pool accepted overlapping buffers");
                    if(runPool(pool,IntPtr.Zero,IntPtr.Zero,IntPtr.Zero,0)!=0)throw new Exception("Empty pool run failed");
                }
                var samples=new double[3];var gcSamples=new double[3];var totals=new double[3];
                for(int run=0;run<3;run++) {
                    for(int i=0;i<actual.Length;i++)actual[i]=unchecked((long)0xccccccccccccccccUL);
                    Marshal.Copy(actual,0,output,actual.Length);
                    var watch=Stopwatch.StartNew();uint error=persistent?runPool(pool,symbol,input,output,(uint)count):map(symbol,input,output,(uint)count,(uint)budgets[b]);watch.Stop();samples[run]=watch.Elapsed.TotalMilliseconds;
                    if(error!=0)throw new Exception("Numeric map error "+error);
                    Marshal.Copy(output,actual,0,actual.Length);
                    for(int i=0;i<actual.Length;i++)if(actual[i]!=expected[i])throw new Exception(method+" mismatch at record "+(i/4)+" field "+(i%4)+" jobs "+budgets[b]);
                    if(useHeap) {
                        var gcWatch=Stopwatch.StartNew();QuiescentGc(module,heap,collect);gcWatch.Stop();gcSamples[run]=gcWatch.Elapsed.TotalMilliseconds;
                    }
                    totals[run]=samples[run]+gcSamples[run];
                }
                Array.Sort(samples);Array.Sort(gcSamples);Array.Sort(totals);results[b]=new Measurement{method=method,jobs=budgets[b],cases=count,median_ms=samples[1],gc_median_ms=gcSamples[1],total_median_ms=totals[1],passed=true};
                if(persistent) {if(destroy(pool)!=0)throw new Exception("Pool destroy failed");pool=IntPtr.Zero;}
            }
            return results;
        }finally {
            if(pool!=IntPtr.Zero&&destroy!=null)destroy(pool);
            if(heap!=IntPtr.Zero&&heapDestroy!=null)heapDestroy(heap);
            if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);
            if(module!=IntPtr.Zero)FreeLibrary(module);if(library!=IntPtr.Zero)FreeLibrary(library);
        }
    }
    public static void CheckBusyAndLifetime(string runtime,string gatePath) {
        IntPtr library=IntPtr.Zero,gateModule=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero,gate=IntPtr.Zero;
        Thread thread=null;Destroy destroy=null;
        try {
            library=LoadLibraryExW(runtime,IntPtr.Zero,0x1100);gateModule=LoadLibraryExW(gatePath,IntPtr.Zero,0x1100);
            if(library==IntPtr.Zero||gateModule==IntPtr.Zero)throw new Exception("Busy probe DLL load failed");
            var create=Marshal.GetDelegateForFunctionPointer<Create>(GetProcAddress(library,"boom_pool_create"));
            var run=Marshal.GetDelegateForFunctionPointer<RunPool>(GetProcAddress(library,"boom_pool_run"));
            destroy=Marshal.GetDelegateForFunctionPointer<Destroy>(GetProcAddress(library,"boom_pool_destroy"));
            var entry=GetProcAddress(gateModule,"boom_probe_gate");if(entry==IntPtr.Zero)throw new Exception("Missing assembly gate");
            gate=Marshal.AllocHGlobal(4);Marshal.WriteInt32(gate,0);input=Marshal.AllocHGlobal(128);output=Marshal.AllocHGlobal(32);Marshal.WriteIntPtr(input,gate);
            pool=create(4);if(pool==IntPtr.Zero)throw new Exception("Pool create failed");uint result=999;Exception failure=null;
            thread=new Thread(()=>{try{result=run(pool,entry,input,output,1);}catch(Exception error){failure=error;}});thread.Start();
            var watch=Stopwatch.StartNew();while(Marshal.ReadInt32(pool,12)==0&&watch.ElapsedMilliseconds<5000)Thread.Yield();
            if(Marshal.ReadInt32(pool,12)!=1)throw new Exception("Pool did not enter the assembly gate");
            if(run(pool,entry,input,output,1)!=170||destroy(pool)!=170)throw new Exception("Busy pool allowed overlapping run/destroy");
            Marshal.WriteInt32(gate,1);if(!thread.Join(10000))throw new Exception("Pool did not leave assembly gate");if(failure!=null)throw failure;if(result!=0)throw new Exception("Busy probe run failed");
            if(destroy(pool)!=0)throw new Exception("Pool failed after rejected destroy");pool=IntPtr.Zero;
            for(int repeat=0;repeat<20;repeat++){pool=create((uint)(repeat%8+1));if(pool==IntPtr.Zero||destroy(pool)!=0)throw new Exception("Repeated lifecycle failed");pool=IntPtr.Zero;}
        }finally {
            if(thread!=null&&thread.IsAlive){if(gate!=IntPtr.Zero)Marshal.WriteInt32(gate,1);thread.Join();}
            if(pool!=IntPtr.Zero&&destroy!=null)destroy(pool);
            if(gate!=IntPtr.Zero)Marshal.FreeHGlobal(gate);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);
            if(gateModule!=IntPtr.Zero)FreeLibrary(gateModule);if(library!=IntPtr.Zero)FreeLibrary(library);
        }
    }
}
'@
$measurements=[Collections.Generic.List[object]]::new()
$selected=if($InheritanceProgram){@('fields','special','array','arrayFault','retained')}elseif($InterfaceProgram){@('choose','nested','wide','reference','nil')}elseif($TypeChecks){@('checks','name','boxCast','referenceJoin','dynamicString')}elseif($ConcatProgram){@('intHash','longHash','nested','interned','arrays')}elseif($MirrorProgram){@('nameHash','flags','component','assignable','array')}elseif($StringProgram){@('hashMix','character','compare','array','state')}elseif($ObjectProgram){@('pair','graph','arrays','wide','nullField')}elseif($LinkedProgram){@('intRoot','longRoot','floatRoot','arrayRoot','arrayFault')}elseif($ReferenceArrays){@('sumArray','arrayField','nullElements')}elseif($ObjectKernels){@('intObject','longObject','linkedObjects','arrayObject','nullCall')}elseif($ArrayKernels){@('intArray','longArray','doubleArray','arrayCalls','bounds')}else{@('longLoop','longDiv','floatMix','doubleMix')}
foreach($method in $selected){
    $manifest=Get-Content -LiteralPath (Join-Path $numericRoot "$method\compilation.json") -Raw|ConvertFrom-Json
    if((Get-FileHash -LiteralPath $manifest.dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $manifest.dll_digest.sha256){throw 'Numeric DLL identity mismatch.'}
    foreach($measurement in [BoomManagedParallelProbe]::Run((Join-Path $root 'boom-runtime.dll'),$manifest.dll,$method,$Count,$Persistent.IsPresent,($InheritanceProgram.IsPresent -or $InterfaceProgram.IsPresent -or $TypeChecks.IsPresent -or $ConcatProgram.IsPresent -or $MirrorProgram.IsPresent -or $StringProgram.IsPresent -or $ObjectProgram.IsPresent -or $ArrayKernels.IsPresent -or $ObjectKernels.IsPresent -or $ReferenceArrays.IsPresent -or ($LinkedProgram.IsPresent -and [bool]$manifest.requires_heap)),$InterfaceProgram.IsPresent,$InheritanceProgram.IsPresent)){$measurements.Add($measurement)}
}
if($Persistent){[BoomManagedParallelProbe]::CheckBusyAndLifetime((Join-Path $root 'boom-runtime.dll'),(Join-Path $root 'fpstate.dll'))}
$report=[ordered]@{runtime_language='assembly';backend=$(if($InheritanceProgram){$numericReport.backend}elseif($InterfaceProgram){'boom-interface-program-v8-masm-x64'}else{'boom-numeric-v1-masm-x64'});persistent_pool=$Persistent.IsPresent;array_kernels=$ArrayKernels.IsPresent;object_kernels=$ObjectKernels.IsPresent;reference_array_kernels=$ReferenceArrays.IsPresent;linked_program_kernels=$LinkedProgram.IsPresent;object_program_kernels=$ObjectProgram.IsPresent;string_program_kernels=$StringProgram.IsPresent;mirror_program_kernels=$MirrorProgram.IsPresent;concat_program_kernels=$ConcatProgram.IsPresent;runtime_type_checks=$TypeChecks.IsPresent;interface_program_kernels=$InterfaceProgram.IsPresent;inheritance_program_kernels=$InheritanceProgram.IsPresent;quiescent_gc_after_batch=($InheritanceProgram.IsPresent -or $InterfaceProgram.IsPresent -or $TypeChecks.IsPresent -or $ConcatProgram.IsPresent -or $MirrorProgram.IsPresent -or $StringProgram.IsPresent -or $ObjectProgram.IsPresent -or $ArrayKernels.IsPresent -or $ObjectKernels.IsPresent -or $ReferenceArrays.IsPresent -or $LinkedProgram.IsPresent);records_per_method=$Count;methods=$selected.Count;workers=@(1,2,4,8);repeats=3;native_record_executions=$Count*$selected.Count*4*3;exception_context_isolated=$true;all_output_fields_checked=$true;busy_and_lifetime_checked=$Persistent.IsPresent;measurements=@($measurements.ToArray());passed=$true;game_integration_complete=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 7
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
