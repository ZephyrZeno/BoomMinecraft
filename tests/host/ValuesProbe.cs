// Development driver only. Conversions, workers, guest allocation and GC are MASM.
using System;
using System.Globalization;
using System.Runtime.InteropServices;
public static class BoomValuesProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,ulong type);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr r,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Class(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(uint id,uint field);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr p,IntPtr fn,IntPtr input,IntPtr output,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr p);
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static IntPtr Open(string p){IntPtr m=LoadLibraryExW(p,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Value conversion DLL load failed");return m;}
    static void Check(bool ok,string message){if(!ok)throw new Exception(message);}
    public static long Decimal(string dll,string runtime,bool wide,uint owner,uint typeField){
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try{
            heap=Fn<Create>(m,"boom_heap_create")(4*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Decimal heap failed");
            IntPtr descriptor=Fn<Class>(m,"boom_get_class_descriptor")(owner),cell=Fn<Field>(m,"boom_get_static_field")(owner,typeField);
            Check(descriptor!=IntPtr.Zero&&cell!=IntPtr.Zero&&Marshal.ReadInt32(descriptor,8)==0&&Marshal.ReadIntPtr(cell)==IntPtr.Zero,"Decimal wrapper initialized before its first active use");
            const int count=2049;long[] args=new long[count*16];uint[] expected=new uint[count];
            for(int i=0;i<count;i++){
                args[i*16]=wide?unchecked((long)(0x8000000000000000UL+(ulong)i*0x123456789abcUL)):unchecked((uint)(0x80000000U+(uint)i*65537));
                string value=wide?args[i*16].ToString(CultureInfo.InvariantCulture):unchecked((int)args[i*16]).ToString(CultureInfo.InvariantCulture);
                uint hash=0;foreach(char c in value)hash=unchecked(hash*31+c);expected[i]=unchecked(hash*31+(uint)value.Length);
            }
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(args,0,input,args.Length);pool=Fn<PoolCreate>(r,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Decimal workers failed");long retained=0;
            for(int batch=0;batch<3;batch++){
                Check(Fn<PoolRun>(r,"boom_pool_run")(pool,GetProcAddress(m,"boom_entry"),input,output,count)==0,"Decimal worker batch failed");
                for(int i=0;i<count;i++)Check(unchecked((uint)Marshal.ReadInt64(output,i*32))==expected[i]&&Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0,"Concurrent decimal conversion changed its value or context");
                Check(Marshal.ReadInt32(descriptor,8)==2&&Marshal.ReadIntPtr(cell)!=IntPtr.Zero,"Original decimal wrapper TYPE initializer did not complete");
                long live=Marshal.ReadInt64(heap,56);if(batch==0){retained=live-count*2;Check(retained>0,"Decimal bootstrap graph missing");}else Check(live==retained+count*2,"Decimal conversion temporary count changed");
                IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n);Check(Fn<Collect>(m,"boom_heap_collect")(heap,roots,n)==(ulong)count*2&&Marshal.ReadInt64(heap,56)==retained,"Decimal bootstrap roots or result reclamation changed");
            }
            return retained;
        }finally{if(pool!=IntPtr.Zero)Fn<PoolDestroy>(r,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Fn<Destroy>(m,"boom_heap_destroy")(heap);FreeLibrary(r);FreeLibrary(m);}
    }
    public static void Parallel(string dll,string runtime,bool boolean){
        IntPtr module=Open(dll),library=Open(runtime),heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try{
            heap=Fn<Create>(module,"boom_heap_create")(4*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Values heap failed");
            const int count=2049;long[] args=new long[count*16];for(int i=0;i<count;i++)args[i*16]=unchecked((uint)(0x80000000U+(uint)i*65537));
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(args,0,input,args.Length);pool=Fn<PoolCreate>(library,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Values workers failed");
            for(int batch=0;batch<3;batch++){
                Check(Fn<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)==0,"Values parallel dispatch failed");
                for(int i=0;i<count;i++){
                    uint expected=boolean?((args[i*16]&1)==0?97196326U:3569041U):unchecked((uint)args[i*16])&65535;
                    Check(unchecked((uint)Marshal.ReadInt64(output,i*32))==expected&&Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0,"Concurrent primitive conversion or literal identity changed");
                }
                Check(Marshal.ReadInt64(heap,56)==(boolean?4:count*2),"Value conversion allocated unexpected guest objects");
                IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out uint n);Check(Fn<Collect>(module,"boom_heap_collect")(heap,roots,n)==(boolean?0UL:(ulong)count*2),"Values temporary reclamation count changed");
                Check(Marshal.ReadInt64(heap,56)==(boolean?4:0),"Value conversion roots leaked or disappeared");
            }
        }finally{if(pool!=IntPtr.Zero)Fn<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);FreeLibrary(library);FreeLibrary(module);}
    }
    public static void InitializationFailure(string dll,string runtime,uint owner,uint initializer){
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero;
        try{
            heap=Fn<Create>(m,"boom_heap_create")(4096);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Decimal failure heap failed");
            ulong prefill=checked((ulong)Marshal.ReadInt64(heap,16)-288);
            Check(Fn<Alloc>(r,"boom_heap_alloc")(heap,prefill,0,1)!=IntPtr.Zero,"Decimal failure prefill failed");
            IntPtr descriptor=Fn<Class>(m,"boom_get_class_descriptor")(owner);var entry=Fn<Entry>(m,"boom_entry");var c=new Context();entry(ref c,new ulong[]{123});
            Check(c.Kind==3&&c.Method==initializer&&c.Depth==0&&Marshal.ReadInt32(descriptor,8)==3,"Decimal initializer OOM lost its original source or erroneous state");
            IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n);Check(Fn<Collect>(m,"boom_heap_collect")(heap,roots,n)>0,"Failed initializer temporary storage was not reclaimed");
            c=new Context();entry(ref c,new ulong[]{123});Check(c.Kind==9&&c.Depth==0&&Marshal.ReadInt32(descriptor,8)==3,"Decimal initialization was retried after a persistent failure");
        }finally{if(heap!=IntPtr.Zero)Fn<Destroy>(m,"boom_heap_destroy")(heap);FreeLibrary(r);FreeLibrary(m);}
    }
    public static void Budget(string dll,uint method){
        IntPtr module=Open(dll),heap=IntPtr.Zero;
        try{
            heap=Fn<Create>(module,"boom_heap_create")(4096);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Small values heap failed");var entry=Fn<Entry>(module,"boom_entry");bool failed=false;
            for(int i=0;i<256;i++){var c=new Context();entry(ref c,new ulong[]{0xd800});if(c.Kind!=0){Check(c.Kind==3&&c.Method==method&&c.Depth==0,"Value OOM origin or depth changed");failed=true;break;}}
            Check(failed&&Marshal.ReadInt64(heap,56)>0,"Value conversion ignored the small heap budget");
            IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out uint n);Check(Fn<Collect>(module,"boom_heap_collect")(heap,roots,n)>0&&Marshal.ReadInt64(heap,56)==0,"Value OOM temporary graph leaked");
            var ok=new Context();Check(entry(ref ok,new ulong[]{0xd800})==0xd800UL*32+7&&ok.Kind==0&&ok.Depth==0,"Value conversion did not recover after collection");
        }finally{if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);FreeLibrary(module);}
    }
}
