$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$root=Join-Path $projectRoot ('.boom\array-tests\'+[guid]::NewGuid().ToString('N'))
& (Join-Path $PSScriptRoot 'Build-AssemblyRuntime.ps1') -Output $root
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
public static class BoomArrayProbe {
    [StructLayout(LayoutKind.Sequential)] public struct Context {public uint Kind,PC,Method,Reserved;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr LoadLibraryExW(string p,IntPtr zero,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)]static extern IntPtr GetProcAddress(IntPtr m,string name);
    [DllImport("kernel32.dll")]static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Create(ulong budget);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Allocate(IntPtr heap,ulong bytes,uint refs,ulong type);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr New(IntPtr heap,int length,uint kind,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Length(IntPtr array,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Load(IntPtr array,int index,uint kind,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Store(IntPtr array,int index,ulong bits,uint kind,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Copy(IntPtr src,int srcPos,IntPtr dst,int dstPos,int count,ref Context context);
    static void Check(bool b,string message){if(!b)throw new Exception(message);}
    static ulong Normalize(uint kind,ulong bits){unchecked{switch(kind){case 4:return bits&1;case 5:return (ushort)bits;case 8:return (uint)(sbyte)(byte)bits;case 9:return (uint)(short)(ushort)bits;case 6:case 10:return (uint)bits;default:return bits;}}}
    static ulong GC(Collect collect,IntPtr heap,params IntPtr[] roots){IntPtr p=IntPtr.Zero;try{if(roots.Length>0){p=Marshal.AllocHGlobal(roots.Length*8);for(int i=0;i<roots.Length;i++)Marshal.WriteIntPtr(p,i*8,roots[i]);}return collect(heap,p,(uint)roots.Length);}finally{if(p!=IntPtr.Zero)Marshal.FreeHGlobal(p);}}
    public static void Run(string dll){
        IntPtr module=LoadLibraryExW(dll,IntPtr.Zero,0x1100),heap=IntPtr.Zero;Destroy destroy=null;Check(module!=IntPtr.Zero,"Runtime load failed");
        try{
            var create=Marshal.GetDelegateForFunctionPointer<Create>(GetProcAddress(module,"boom_heap_create"));destroy=Marshal.GetDelegateForFunctionPointer<Destroy>(GetProcAddress(module,"boom_heap_destroy"));
            var allocate=Marshal.GetDelegateForFunctionPointer<Allocate>(GetProcAddress(module,"boom_heap_alloc"));var collect=Marshal.GetDelegateForFunctionPointer<Collect>(GetProcAddress(module,"boom_heap_collect"));
            var make=Marshal.GetDelegateForFunctionPointer<New>(GetProcAddress(module,"boom_array_new"));var length=Marshal.GetDelegateForFunctionPointer<Length>(GetProcAddress(module,"boom_array_length"));
            var load=Marshal.GetDelegateForFunctionPointer<Load>(GetProcAddress(module,"boom_array_load"));var store=Marshal.GetDelegateForFunctionPointer<Store>(GetProcAddress(module,"boom_array_store"));var copy=Marshal.GetDelegateForFunctionPointer<Copy>(GetProcAddress(module,"boom_array_copy"));
            heap=create(16*1024*1024);Check(heap!=IntPtr.Zero,"Heap create failed");
            for(uint kind=4;kind<=11;kind++){
                var context=new Context();var array=make(heap,64,kind,ref context);var other=make(heap,64,kind,ref context);Check(array!=IntPtr.Zero&&other!=IntPtr.Zero&&context.Kind==0,"Array create failed");
                Check(length(array,ref context)==64&&context.Kind==0,"Array length mismatch");var expected=new ulong[64];uint opcodeKind=kind==4?8:kind;
                for(int i=0;i<64;i++){
                    Check(load(array,i,opcodeKind,ref context)==0&&context.Kind==0,"Array not zero initialized");
                    ulong bits=unchecked((ulong)i*0xfedcba9876543210UL+0x7ff0000000000001UL);expected[i]=Normalize(kind,bits);store(array,i,bits,opcodeKind,ref context);Check(context.Kind==0,"Store failed");
                }
                copy(array,0,array,3,50,ref context);Array.Copy(expected,0,expected,3,50);Check(context.Kind==0,"Backward overlapping copy failed");
                copy(array,7,array,0,40,ref context);Array.Copy(expected,7,expected,0,40);Check(context.Kind==0,"Forward overlapping copy failed");
                copy(array,2,array,2,10,ref context);copy(array,64,array,64,0,ref context);Check(context.Kind==0,"Self/empty copy failed");
                for(int i=0;i<64;i++)Check(load(array,i,opcodeKind,ref context)==expected[i]&&context.Kind==0,"Primitive array bits mismatch, kind "+kind);
                copy(array,0,other,0,64,ref context);Check(context.Kind==0,"Separate array copy failed");
                for(int i=0;i<64;i++)Check(load(other,i,opcodeKind,ref context)==expected[i],"Separate array contents mismatch");
                Check(GC(collect,heap,array,other)==0&&GC(collect,heap)==2,"Primitive array GC metadata mismatch");
            }
            var ctx=new Context();Check(make(heap,-1,10,ref ctx)==IntPtr.Zero&&ctx.Kind==2,"Negative array length accepted");
            ctx=new Context();Check(make(heap,int.MaxValue,11,ref ctx)==IntPtr.Zero&&ctx.Kind==3,"Oversized array accepted");
            ctx=new Context();Check(make(heap,3,3,ref ctx)==IntPtr.Zero&&ctx.Kind==7,"Invalid kind accepted");
            ctx=new Context();var empty=make(heap,0,10,ref ctx);Check(empty!=IntPtr.Zero&&length(empty,ref ctx)==0,"Empty array failed");
            load(empty,0,10,ref ctx);Check(ctx.Kind==5,"Empty array access accepted");
            ctx=new Context();length(IntPtr.Zero,ref ctx);Check(ctx.Kind==4,"Null length accepted");
            ctx=new Context();load(IntPtr.Zero,0,10,ref ctx);Check(ctx.Kind==4,"Null load accepted");
            ctx=new Context();store(IntPtr.Zero,0,0,10,ref ctx);Check(ctx.Kind==4,"Null store accepted");
            ctx=new Context();var small=make(heap,4,10,ref ctx);var different=make(heap,4,9,ref ctx);
            foreach(int index in new[]{-1,4,int.MaxValue}){ctx=new Context();load(small,index,10,ref ctx);Check(ctx.Kind==5,"Out of bounds load accepted");ctx=new Context();store(small,index,7,10,ref ctx);Check(ctx.Kind==5,"Out of bounds store accepted");}
            ctx=new Context();copy(small,0,different,0,0,ref ctx);Check(ctx.Kind==6,"Mismatched array types accepted");
            ctx=new Context();copy(small,int.MaxValue,small,0,1,ref ctx);Check(ctx.Kind==5,"Copy range overflow accepted");
            ctx=new Context();copy(small,0,small,0,-1,ref ctx);Check(ctx.Kind==5,"Negative copy length accepted");
            ctx=new Context();copy(IntPtr.Zero,0,small,0,0,ref ctx);Check(ctx.Kind==4,"Null copy accepted");
            Check(destroy(heap)!=0,"Heap destroy failed");heap=IntPtr.Zero;

            heap=create(16*1024*1024);ctx=new Context();var references=make(heap,4,12,ref ctx);var referenceCopy=make(heap,4,12,ref ctx);
            var a=allocate(heap,8,0,1);var b=allocate(heap,8,0,1);var garbage=allocate(heap,8,0,1);Check(garbage!=IntPtr.Zero,"Reference target allocation failed");
            store(references,0,unchecked((ulong)a.ToInt64()),12,ref ctx);store(references,1,unchecked((ulong)b.ToInt64()),12,ref ctx);copy(references,0,referenceCopy,0,4,ref ctx);Check(ctx.Kind==0,"Reference copy failed");
            Check(GC(collect,heap,referenceCopy)==2,"Reference array failed to trace live targets");
            Check(load(referenceCopy,0,12,ref ctx)==unchecked((ulong)a.ToInt64())&&load(referenceCopy,1,12,ref ctx)==unchecked((ulong)b.ToInt64()),"Reference pointers changed");
            Check(GC(collect,heap)==3,"Reference array graph was not reclaimed");
            var shared=make(heap,8000,10,ref ctx);Check(shared!=IntPtr.Zero,"Concurrent array allocation failed");
            Parallel.For(0,8,worker=>{var local=new Context();for(int n=0;n<1000;n++){int index=worker*1000+n;store(shared,index,(ulong)(index+17),10,ref local);Check(local.Kind==0,"Disjoint array store failed");}});
            for(int i=0;i<8000;i++)Check(load(shared,i,10,ref ctx)==(ulong)(i+17),"Concurrent array value mismatch");
            Check(GC(collect,heap,shared)==0&&GC(collect,heap)==1,"Concurrent array collection failed");
            Check(destroy(heap)!=0,"Final heap destroy failed");heap=IntPtr.Zero;
        }finally{if(heap!=IntPtr.Zero&&destroy!=null)destroy(heap);FreeLibrary(module);}
    }
}
'@
[BoomArrayProbe]::Run((Join-Path $root 'boom-runtime.dll'))
$report=[ordered]@{implementation_language='assembly';passed=$true;primitive_kinds=8;untyped_reference_arrays=$true;overlapping_copies=$true;null_and_bounds_checked=$true;budget_and_negative_length_checked=$true;gc_reference_trace=$true;disjoint_parallel_stores=8000;java_bytecode_lowering_exercised_by_this_test=$false;class_assignability_integrated=$false;game_integration_complete=$false;run_directory=$root}
$json=$report|ConvertTo-Json -Depth 5
[IO.File]::WriteAllText((Join-Path $root 'result.json'),$json,[Text.UTF8Encoding]::new($false));Write-Output $json
