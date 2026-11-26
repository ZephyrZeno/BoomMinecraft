// Test host only. Resource lookup, file IO, hashing, Java methods, monitors and workers are MASM.
using System;
using System.Runtime.InteropServices;
public static class BoomResourceProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string path,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll")] static extern bool GetProcessHandleCount(IntPtr process,out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context ctx,[In] ulong[] values);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint workers);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int PoolRun(IntPtr pool,IntPtr entry,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int PoolDestroy(IntPtr pool);
    static void Check(bool yes,string message){if(!yes)throw new Exception(message);}
    static IntPtr Open(string path){IntPtr m=LoadLibraryExW(path,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Resource DLL load failed");return m;}
    static T Fn<T>(IntPtr m,string name){IntPtr p=GetProcAddress(m,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    public static void Parallel(string dll,string runtime,uint expected) {
        IntPtr module=Open(dll),library=Open(runtime),heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try{
            heap=Fn<Create>(module,"boom_heap_create")(16*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Resource heap binding failed");
            pool=Fn<PoolCreate>(library,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Resource pool creation failed");
            const int count=2049;input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(new long[count*16],0,input,count*16);
            long retained=-1;uint previousHandles=0;
            for(int batch=0;batch<3;batch++){
                Check(Fn<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)==0,"Concurrent resource dispatch failed");
                for(int i=0;i<count;i++)Check(unchecked((uint)Marshal.ReadInt64(output,i*32))==expected&&Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0,"Concurrent resource bytes/context mismatch");
                Check(Marshal.ReadInt64(heap,112)==0,"Resource stream monitor leaked");
                IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out uint rootCount);Check(Fn<Collect>(module,"boom_heap_collect")(heap,roots,rootCount)!=ulong.MaxValue,"Resource post-batch GC failed");
                long live=Marshal.ReadInt64(heap,56);Check(live>0&&(retained<0||retained==live),"Resource temporary buffers/streams leaked or roots changed");retained=live;
                Check(GetProcessHandleCount(GetCurrentProcess(),out uint handles),"Handle count unavailable");if(batch>0)Check(handles<=previousHandles+1,"Resource file handles grew across batches");previousHandles=handles;
            }
        }finally{if(pool!=IntPtr.Zero)Fn<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);FreeLibrary(library);FreeLibrary(module);}
    }
    public static void Budget(string dll){
        IntPtr module=Open(dll),heap=IntPtr.Zero;
        try{
            heap=Fn<Create>(module,"boom_heap_create")(4096);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Small resource heap failed");
            var entry=Fn<Entry>(module,"boom_entry");var ctx=new Context();entry(ref ctx,new ulong[]{9,1,0});Check(ctx.Kind==3&&ctx.Depth==0&&Marshal.ReadInt64(heap,112)==0,"Resource bytes ignored budget or leaked a monitor");
            IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out uint rootCount);Check(Fn<Collect>(module,"boom_heap_collect")(heap,roots,rootCount)!=ulong.MaxValue,"Resource OOM recovery GC failed");
            ctx=new Context();ulong result=entry(ref ctx,new ulong[]{4,0,0});Check(ctx.Kind==0&&unchecked((uint)result)==unchecked((uint)-777),"Resource lookup did not recover after explicit collection");
        }finally{if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);FreeLibrary(module);}
    }
}
