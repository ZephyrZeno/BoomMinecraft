// Development host only: JDK bytecode and runtime/pool/heap execution are MASM.
using System;
using System.Runtime.InteropServices;
public static class BoomBootstrapProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context ctx,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int PoolRun(IntPtr pool,IntPtr entry,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int PoolDestroy(IntPtr pool);
    static T Symbol<T>(IntPtr module,string name){IntPtr p=GetProcAddress(module,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static void Check(bool value,string message){if(!value)throw new Exception(message);}
    static IntPtr Open(string path){IntPtr p=LoadLibraryExW(path,IntPtr.Zero,0x1100);Check(p!=IntPtr.Zero,"Native bootstrap module load failed");return p;}
    public static void Cold(string dll,string runtime){
        IntPtr module=Open(dll),library=IntPtr.Zero,heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try {
            library=Open(runtime);heap=Symbol<Create>(module,"boom_heap_create")(16*1024*1024);
            Check(heap!=IntPtr.Zero&&Symbol<Bind>(module,"boom_bind_heap")(heap)==1,"Bootstrap heap binding failed");
            const int count=8195;var values=new long[count*16];
            for(int i=0;i<count;i++){values[i*16]=i==0?0:i*2+1;values[i*16+1]=-17000-i;}
            input=Marshal.AllocHGlobal(values.Length*8);Marshal.Copy(values,0,input,values.Length);
            output=Marshal.AllocHGlobal(count*32);pool=Symbol<PoolCreate>(library,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Bootstrap pool creation failed");
            Check(Symbol<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)==0,"Bootstrap pool run failed");
            var results=new long[count*4];Marshal.Copy(output,results,0,results.Length);
            for(int i=0;i<count;i++){
                int value=(int)values[i*16],fallback=(int)values[i*16+1];
                uint expected=unchecked((uint)((i==0?fallback:value)^(i==0?0x3c:0x5a)^(i==0?0x1234:0x5678)));
                Check(unchecked((ulong)results[i*4])==expected&&results[i*4+1]==0&&results[i*4+2]==0&&results[i*4+3]==0,"Bootstrap result/context mismatch at "+i);
            }
            Check(Marshal.ReadInt64(heap,56)==count,"Bootstrap EMPTY initialized more than once or per-call object lost");
            uint rootCount;IntPtr roots=Symbol<Roots>(module,"boom_get_static_roots")(out rootCount);
            Check(rootCount>0&&Symbol<Collect>(module,"boom_heap_collect")(heap,roots,rootCount)==count-1&&Marshal.ReadInt64(heap,56)==1,"Bootstrap static singleton root was lost");
            var context=new Context();ulong actual=Symbol<Entry>(module,"boom_entry")(ref context,new ulong[]{0,7});
            Check(actual==(7U^0x3cU^0x1234U)&&context.Kind==0&&Marshal.ReadInt64(heap,56)==1,"Bootstrap singleton changed after GC");
        } finally {if(pool!=IntPtr.Zero)Symbol<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Symbol<Destroy>(module,"boom_heap_destroy")(heap);if(library!=IntPtr.Zero)FreeLibrary(library);FreeLibrary(module);}
    }
    public static void Retained(string dll){
        IntPtr module=Open(dll),heap=IntPtr.Zero;
        try {
            heap=Symbol<Create>(module,"boom_heap_create")(1024*1024);Check(heap!=IntPtr.Zero&&Symbol<Bind>(module,"boom_bind_heap")(heap)==1,"Retained bootstrap heap failed");
            var entry=Symbol<Entry>(module,"boom_entry");var ctx=new Context();
            Check(entry(ref ctx,new ulong[]{123})==123&&ctx.Kind==0,"Retained JDK object creation failed");ctx=new Context();
            Check(entry(ref ctx,new ulong[]{999})==123&&ctx.Kind==0&&Marshal.ReadInt64(heap,56)==2,"Retained bootstrap object identity changed");
            uint count;IntPtr roots=Symbol<Roots>(module,"boom_get_static_roots")(out count);var collect=Symbol<Collect>(module,"boom_heap_collect");
            Check(count>=2&&collect(heap,roots,count)==0&&Marshal.ReadInt64(heap,56)==2,"Cross-loader static reference was not traced");
            IntPtr held=Marshal.ReadIntPtr(roots);Check(held!=IntPtr.Zero&&Marshal.ReadInt32(held)==123&&Marshal.ReadByte(held,4)==1,"JDK compact private fields changed");
            // Development-only removal of the application static root; the JDK EMPTY
            // slot remains a root and must survive. No user world is involved.
            Marshal.WriteIntPtr(roots,IntPtr.Zero);Check(collect(heap,roots,count)==1&&Marshal.ReadInt64(heap,56)==1,"Dropping application root reclaimed the wrong bootstrap object");
            ctx=new Context();Check(entry(ref ctx,new ulong[]{456})==456&&ctx.Kind==0,"Bootstrap allocation after collection failed");
        } finally {if(heap!=IntPtr.Zero)Symbol<Destroy>(module,"boom_heap_destroy")(heap);FreeLibrary(module);}
    }
}
