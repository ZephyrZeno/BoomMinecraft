// Development driver only. CDS services, Java initialization and workers are MASM.
using System;
using System.Runtime.InteropServices;
public static class BoomCdsProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Service(ref Context c,IntPtr args,IntPtr profile,uint op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr r,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Class(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(uint id,uint field);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr p,IntPtr fn,IntPtr input,IntPtr output,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr p);
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static IntPtr Open(string p){IntPtr m=LoadLibraryExW(p,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"CDS DLL load failed");return m;}
    static void Check(bool ok,string s){if(!ok)throw new Exception(s);}
    public static void Abi(string runtime){
        IntPtr m=Open(runtime),p=Marshal.AllocHGlobal(32),pool=Marshal.AllocHGlobal(64),args=Marshal.AllocHGlobal(8);
        try{
            for(int i=0;i<64;i+=8)Marshal.WriteInt64(pool,i,0);
            for(int i=0;i<32;i+=8)Marshal.WriteInt64(p,i,0);
            Marshal.WriteInt32(p,0,0x43445350);Marshal.WriteInt32(p,4,1);Marshal.WriteIntPtr(p,16,pool);Marshal.WriteIntPtr(args,IntPtr.Zero);
            var call=Fn<Service>(m,"boom_cds_service");
            for(uint op=1;op<=4;op++){var c=new Context();Check(call(ref c,args,p,op)==0&&c.Kind==0,"No-CDS flags or seed changed");}
            foreach(int offset in new int[]{0,4,8,12,16,24}){
                long saved=Marshal.ReadInt64(p,offset);Marshal.WriteInt64(p,offset,offset==16?0:17);
                var c=new Context{PC=13,Method=71};Check(call(ref c,args,p,1)==0&&c.Kind==7&&c.PC==13&&c.Method==71,"Unsupported CDS profile accepted");Marshal.WriteInt64(p,offset,saved);
            }
            var bad=new Context();call(ref bad,args,p,5);Check(bad.Kind==7,"Unknown CDS operation accepted");
            bad=new Context();call(ref bad,IntPtr.Zero,p,0);Check(bad.Kind==7,"Missing Class argument vector accepted");
            bad=new Context();call(ref bad,args,p,0);Check(bad.Kind==4,"Null Class mirror accepted");
            var pending=new Context{Kind=3,PC=19,Method=71,Depth=2};call(ref pending,args,IntPtr.Zero,999);Check(pending.Kind==3&&pending.PC==19&&pending.Method==71&&pending.Depth==2,"CDS service overwrote a pending failure");
        }finally{Marshal.FreeHGlobal(args);Marshal.FreeHGlobal(pool);Marshal.FreeHGlobal(p);FreeLibrary(m);}
    }
    public static long Parallel(string dll,string runtime,uint cdsId,uint excludeField){
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try{
            heap=Fn<Create>(m,"boom_heap_create")(1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"CDS heap failed");
            IntPtr descriptor=Fn<Class>(m,"boom_get_class_descriptor")(cdsId);Check(descriptor!=IntPtr.Zero&&Marshal.ReadInt32(descriptor,8)==0,"CDS initializer was already executed");
            const int count=2049;long[] args=new long[count*16];for(int i=0;i<count;i++)args[i*16]=unchecked((uint)(0x80000000U+(uint)i*16777619));
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(args,0,input,args.Length);pool=Fn<PoolCreate>(r,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"CDS workers failed");long live=0;
            string[] flags={"-XX:DumpLoadedClassList=","-XX:+RecordDynamicDumpInfo","-Xshare:","-XX:SharedClassListFile=","-XX:SharedArchiveFile=","-XX:ArchiveClassesAtExit="};
            for(int batch=0;batch<3;batch++){
                Check(Fn<PoolRun>(r,"boom_pool_run")(pool,GetProcAddress(m,"boom_entry"),input,output,count)==0,"CDS worker batch failed");
                for(int i=0;i<count;i++)Check(unchecked((uint)Marshal.ReadInt64(output,i*32))==unchecked((uint)args[i*16])&&Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0,"Concurrent no-archive initialization changed results");
                Check(Marshal.ReadInt32(descriptor,8)==2&&Marshal.ReadInt32(descriptor,12)==0,"Original CDS class initialization did not complete");
                IntPtr cell=Fn<Field>(m,"boom_get_static_field")(cdsId,excludeField);Check(cell!=IntPtr.Zero,"Missing original CDS exclusion field");IntPtr array=Marshal.ReadIntPtr(cell);
                Check(array!=IntPtr.Zero&&Marshal.ReadInt64(array,-16)==48&&Marshal.ReadInt32(array,-20)==6,"Original CDS initializer did not build its array");
                for(int i=0;i<flags.Length;i++){IntPtr text=Marshal.ReadIntPtr(array,i*8);Check(text!=IntPtr.Zero,"Missing initialized CDS flag String");IntPtr chars=Marshal.ReadIntPtr(text);Check(chars!=IntPtr.Zero&&Marshal.PtrToStringUni(chars,checked((int)Marshal.ReadInt64(chars,-16)/2))==flags[i],"Original CDS array contents changed");}
                if(batch==0){live=Marshal.ReadInt64(heap,56);Check(live>0,"CDS bootstrap allocations missing");}else Check(Marshal.ReadInt64(heap,56)==live,"CDS calls allocated new guest objects after warmup");
                IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n);Check(Fn<Collect>(m,"boom_heap_collect")(heap,roots,n)==0&&Marshal.ReadInt64(heap,56)==live,"CDS static graph was lost or temporaries leaked");
            }
            return live;
        }finally{if(pool!=IntPtr.Zero)Fn<PoolDestroy>(r,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Fn<Destroy>(m,"boom_heap_destroy")(heap);FreeLibrary(r);FreeLibrary(m);}
    }
}
