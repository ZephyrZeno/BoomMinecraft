// Development host only. Lazy initialization, getters and workers execute MASM.
using System;
using System.Runtime.InteropServices;
public static class BoomInitializationProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Class(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(uint n,uint f);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,uint tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr p,IntPtr fn,IntPtr input,IntPtr output,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr p);
    static void Check(bool ok,string s){if(!ok)throw new Exception(s);}
    static IntPtr Open(string p){IntPtr m=LoadLibraryExW(p,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Initialization DLL load failed");return m;}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    public static void Parallel(string dll,string runtime,uint owner,uint shared,uint accessField,int increment) {
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try {
            heap=Fn<Create>(m,"boom_heap_create")(1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Initialization heap failed");
            IntPtr descriptor=Fn<Class>(m,"boom_get_class_descriptor")(owner),secrets=Fn<Class>(m,"boom_get_class_descriptor")(shared),cell=Fn<Field>(m,"boom_get_static_field")(shared,accessField);
            Check(Marshal.ReadInt32(descriptor,8)==0&&Marshal.ReadInt32(secrets,8)==0&&Marshal.ReadIntPtr(cell)==IntPtr.Zero,"Lazy target was initialized before its first request");
            const int count=2049;long[] args=new long[count*16];for(int i=0;i<count;i++)args[i*16]=unchecked(0x80000000U+(uint)i*65537);
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(args,0,input,args.Length);pool=Fn<PoolCreate>(r,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Initialization workers failed");
            for(int batch=0;batch<3;batch++) {
                Check(Fn<PoolRun>(r,"boom_pool_run")(pool,GetProcAddress(m,"boom_entry"),input,output,count)==0,"Initialization batch failed");
                for(int i=0;i<count;i++)Check(unchecked((uint)Marshal.ReadInt64(output,i*32))==unchecked((uint)args[i*16]+(uint)increment)&&Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0,"Concurrent lazy getter changed a result/context");
                Check(Marshal.ReadInt32(descriptor,8)==2&&Marshal.ReadInt32(secrets,8)==2&&Marshal.ReadIntPtr(cell)!=IntPtr.Zero,"Lazy target or registration did not finish");
                Check(Marshal.ReadInt64(heap,56)==5,"Lazy initialization allocated duplicates or hot-path guest objects: "+Marshal.ReadInt64(heap,56));
                IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n);Check(Fn<Collect>(m,"boom_heap_collect")(heap,roots,n)==0&&Marshal.ReadInt64(heap,56)==5,"Lazy getter roots were not retained");
            }
        } finally {if(pool!=IntPtr.Zero)Fn<PoolDestroy>(r,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Fn<Destroy>(m,"boom_heap_destroy")(heap);FreeLibrary(r);FreeLibrary(m);}
    }
    public static void Failure(string dll,string runtime,uint owner,uint initializer) {
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero;
        try {
            heap=Fn<Create>(m,"boom_heap_create")(4096);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Initialization failure heap failed");
            ulong prefill=checked((ulong)Marshal.ReadInt64(heap,16)-288);Check(Fn<Alloc>(r,"boom_heap_alloc")(heap,prefill,0,1)!=IntPtr.Zero,"Initialization prefill failed");
            IntPtr descriptor=Fn<Class>(m,"boom_get_class_descriptor")(owner);var entry=Fn<Entry>(m,"boom_entry");var c=new Context();entry(ref c,new ulong[]{123});
            Check(c.Kind==3&&c.Method==initializer&&c.Depth==0&&Marshal.ReadInt32(descriptor,8)==3,"Lazy initializer OOM lost its source or erroneous state: kind="+c.Kind+", method="+c.Method+", state="+Marshal.ReadInt32(descriptor,8));
            IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n);Check(Fn<Collect>(m,"boom_heap_collect")(heap,roots,n)>0,"Initialization prefill was not reclaimed");
            c=new Context();entry(ref c,new ulong[]{123});Check(c.Kind==9&&c.Depth==0&&Marshal.ReadInt32(descriptor,8)==3,"Lazy initialization retried after its persistent failure");
        } finally {if(heap!=IntPtr.Zero)Fn<Destroy>(m,"boom_heap_destroy")(heap);FreeLibrary(r);FreeLibrary(m);}
    }
}
