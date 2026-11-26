param()
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=Join-Path $projectRoot ('.boom\heap-tests\'+[guid]::NewGuid().ToString('N'))
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
# Diagnostic host only; allocation, zeroing, graph tracing, sweep, coalescing,
# synchronization and budget enforcement execute in the assembly DLL.
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
public static class BoomHeapProbe {
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong budget);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Allocate(IntPtr heap,ulong bytes,uint refs,ulong type);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    static void Check(bool value,string message){if(!value)throw new Exception(message);}
    static ulong GC(Collect collect,IntPtr heap,params IntPtr[] roots) {
        IntPtr buffer=IntPtr.Zero;
        try {if(roots.Length!=0){buffer=Marshal.AllocHGlobal(checked(roots.Length*IntPtr.Size));for(int i=0;i<roots.Length;i++)Marshal.WriteIntPtr(buffer,i*8,roots[i]);}return collect(heap,buffer,(uint)roots.Length);}
        finally{if(buffer!=IntPtr.Zero)Marshal.FreeHGlobal(buffer);}
    }
    public static void Run(string runtime) {
        IntPtr module=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;
        Check(module!=IntPtr.Zero,"Heap DLL load failed");Destroy destroy=null;
        try {
            var create=Marshal.GetDelegateForFunctionPointer<Create>(GetProcAddress(module,"boom_heap_create"));
            var allocate=Marshal.GetDelegateForFunctionPointer<Allocate>(GetProcAddress(module,"boom_heap_alloc"));
            var collect=Marshal.GetDelegateForFunctionPointer<Collect>(GetProcAddress(module,"boom_heap_collect"));
            destroy=Marshal.GetDelegateForFunctionPointer<Destroy>(GetProcAddress(module,"boom_heap_destroy"));
            Check(create(0)==IntPtr.Zero&&create(4095)==IntPtr.Zero&&create(1073741825)==IntPtr.Zero,"Invalid heap budgets accepted");
            heap=create(16*1024*1024);Check(heap!=IntPtr.Zero,"Heap create failed");
            Marshal.WriteInt32(heap,4,0);
            Check(allocate(heap,8,0,1)==IntPtr.Zero&&GC(collect,heap)==ulong.MaxValue&&destroy(heap)==0,"Incompatible heap ABI accepted");
            Marshal.WriteInt32(heap,4,1);
            Check(allocate(heap,1,1,1)==IntPtr.Zero&&allocate(heap,32,0,0)==IntPtr.Zero&&allocate(heap,ulong.MaxValue,0,1)==IntPtr.Zero,"Invalid allocation accepted");
            IntPtr a=allocate(heap,24,2,1),b=allocate(heap,24,2,1),c=allocate(heap,24,2,1),cycle=allocate(heap,24,2,1),array=allocate(heap,64,8,2),zero=allocate(heap,0,0,3);
            Check(a!=IntPtr.Zero&&b!=IntPtr.Zero&&c!=IntPtr.Zero&&cycle!=IntPtr.Zero&&array!=IntPtr.Zero&&zero!=IntPtr.Zero,"Graph allocation failed");
            Check(Marshal.ReadInt64(a)==0&&Marshal.ReadInt64(a,8)==0&&Marshal.ReadInt64(a,16)==0,"New memory not zeroed");
            Marshal.WriteIntPtr(a,0,b);Marshal.WriteIntPtr(a,8,c);Marshal.WriteInt64(a,16,0x123456789abcdef);
            Marshal.WriteIntPtr(b,0,a);Marshal.WriteIntPtr(cycle,0,cycle);Marshal.WriteIntPtr(array,0,a);
            for(int i=0;i<1000;i++)Check(allocate(heap,32,0,4)!=IntPtr.Zero,"Garbage allocation failed");
            Check(GC(collect,heap,array,zero)==1001,"Cycle/unreachable graph collection mismatch");
            Check(Marshal.ReadInt64(a,16)==0x123456789abcdef,"Live primitive field changed");
            Check(Marshal.ReadInt64(heap,56)==5,"Unexpected live object count");
            long live=Marshal.ReadInt64(heap,56);
            Check(GC(collect,heap,new IntPtr(1))==ulong.MaxValue,"Invalid root accepted");
            Check(Marshal.ReadInt64(heap,56)==live,"Invalid roots reclaimed objects");
            Check(GC(collect,heap)==5,"Dropping roots did not reclaim live cycle");
            Check(destroy(heap)!=0,"Heap destroy failed");heap=IntPtr.Zero;

            heap=create(65536);Check(heap!=IntPtr.Zero,"Small heap create failed");
            var objects=new List<IntPtr>();IntPtr item;
            while((item=allocate(heap,32,0,5))!=IntPtr.Zero){objects.Add(item);Marshal.WriteInt64(item,-1);}
            Check(objects.Count>20,"Small heap exhausted too early");
            Check(GC(collect,heap,objects[0],objects[objects.Count-1])==(ulong)(objects.Count-2),"Small heap sweep mismatch");
            ulong bigBytes=(ulong)(objects.Count-4)*64;
            IntPtr big=allocate(heap,bigBytes,0,6);Check(big!=IntPtr.Zero,"Adjacent free blocks were not coalesced");
            for(int i=0;i<(int)bigBytes;i+=8)Check(Marshal.ReadInt64(big,i)==0,"Reused memory not zeroed");
            Check(GC(collect,heap)==3,"Large allocation reclaim mismatch");Check(destroy(heap)!=0,"Small heap destroy failed");heap=IntPtr.Zero;

            heap=create(4096);objects.Clear();while((item=allocate(heap,0,0,7))!=IntPtr.Zero)objects.Add(item);
            Check(GC(collect,heap,objects.ToArray())==0,"Zero-size object at arena boundary was rejected");
            Check(GC(collect,heap)==(ulong)objects.Count,"Zero-size objects not reclaimed");
            ulong capacity=(ulong)Marshal.ReadInt64(heap,16);Check(allocate(heap,capacity-32,0,8)!=IntPtr.Zero,"Whole arena reuse failed");
            Check(allocate(heap,0,0,8)==IntPtr.Zero,"Budget exceeded");Check(destroy(heap)!=0,"Boundary heap destroy failed");heap=IntPtr.Zero;

            heap=create(16*1024*1024);var concurrent=new IntPtr[8000];IntPtr sharedHeap=heap;
            Parallel.For(0,8,worker=>{for(int n=0;n<1000;n++){int index=worker*1000+n;var value=allocate(sharedHeap,32,0,9);Check(value!=IntPtr.Zero,"Concurrent OOM");Marshal.WriteInt64(value,index+1);concurrent[index]=value;}});
            Check(new HashSet<IntPtr>(concurrent).Count==concurrent.Length,"Concurrent allocations overlap");
            Check(GC(collect,heap,concurrent)==0,"Concurrent roots lost");
            for(int i=0;i<concurrent.Length;i++)Check(Marshal.ReadInt64(concurrent[i])==i+1,"Concurrent object data changed");
            var half=new IntPtr[4000];Array.Copy(concurrent,half,4000);
            Check(GC(collect,heap,half)==4000&&GC(collect,heap)==4000,"Concurrent allocation sweep mismatch");
            Check(Marshal.ReadInt64(heap,48)==0&&Marshal.ReadInt64(heap,56)==0,"Heap accounting did not return to zero");
            Check(destroy(heap)!=0,"Concurrent heap destroy failed");heap=IntPtr.Zero;
        } finally {if(heap!=IntPtr.Zero&&destroy!=null)destroy(heap);FreeLibrary(module);}
    }
}
'@
[BoomHeapProbe]::Run((Join-Path $root 'boom-runtime.dll'))
$report=[ordered]@{implementation_language='assembly';passed=$true;concurrent_allocations=8000;allocator_workers=8;cycle_trace=$true;reference_arrays=$true;zero_initialization=$true;zero_size_boundary=$true;budget_enforced=$true;coalescing_and_reuse=$true;gc_requires_quiescent_mutators=$true;java_stack_maps_integrated=$false;game_integration_complete=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 5
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
