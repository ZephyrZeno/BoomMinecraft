// Development orchestration only. Original Java initializers and field access run in MASM.
using System;
using System.Runtime.InteropServices;
public static class BoomStreamFieldsProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {public uint Kind,PC,Method,Depth;}
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
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr GetPool(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Init(ref Context c,IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Descriptor(ref Context c,IntPtr o,IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ObjectNew(IntPtr h,IntPtr layout,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ArrayNew(IntPtr h,int n,uint kind,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,uint tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr p,IntPtr fn,IntPtr input,IntPtr output,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr p);
    static void Check(bool ok,string s){if(!ok)throw new Exception(s);}
    static IntPtr Open(string p){IntPtr m=LoadLibraryExW(p,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Stream field DLL load failed");return m;}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static void Call(Init f,IntPtr p,uint kind){var c=new Context();Check(f(ref c,p)==0&&c.Kind==kind&&c.Depth==0,"Stream init field-table status changed");}
    static void Metadata(IntPtr runtime,IntPtr source) {
        IntPtr pool=Marshal.AllocHGlobal(32),table=Marshal.AllocHGlobal(32),layout=Marshal.AllocHGlobal(24);
        try {
            var init=Fn<Init>(runtime,"boom_stream_fields_init");var get=Fn<Descriptor>(runtime,"boom_stream_descriptor");
            long[] p=new long[4],t=new long[4],l=new long[3];Marshal.Copy(source,p,0,4);Marshal.Copy(Marshal.ReadIntPtr(source,8),t,0,4);Marshal.Copy(new IntPtr(t[1]),l,0,3);Marshal.Copy(l,0,layout,3);t[1]=layout.ToInt64();Marshal.Copy(t,0,table,4);p[1]=table.ToInt64();p[2]=0;Marshal.Copy(p,0,pool,4);
            var c=new Context();get(ref c,IntPtr.Zero,pool);Check(c.Kind==20,"Stream field lookup accepted unpublished metadata");
            Call(init,pool,0);Call(init,pool,0);Check(Marshal.ReadIntPtr(pool,16)==table,"Stream fd table was not published");
            foreach(int offset in new int[]{0,4,16,20,24}){long saved=Marshal.ReadInt64(table,offset);Marshal.WriteInt64(table,offset,3);Call(init,pool,7);Marshal.WriteInt64(table,offset,saved);}
            foreach(int offset in new int[]{0,4,8,16,20}){int saved=Marshal.ReadInt32(layout,offset);Marshal.WriteInt32(layout,offset,offset==20?65537:0);Call(init,pool,7);Marshal.WriteInt32(layout,offset,saved);}
            Marshal.WriteIntPtr(pool,16,new IntPtr(1));Call(init,pool,7);Marshal.WriteIntPtr(pool,16,table);
            c=new Context{Kind=3,PC=11,Method=9,Depth=2};init(ref c,IntPtr.Zero);get(ref c,IntPtr.Zero,IntPtr.Zero);Check(c.Kind==3&&c.PC==11&&c.Method==9&&c.Depth==2,"Stream field service overwrote a pending error");
        } finally {Marshal.FreeHGlobal(layout);Marshal.FreeHGlobal(table);Marshal.FreeHGlobal(pool);}
    }
    public static void Parallel(string dll,string runtime,uint owner,int increment,int retained,uint fdOwner,uint outputField,uint accessField,uint sharedOwner,uint sharedField) {
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero,workers=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try {
            heap=Fn<Create>(m,"boom_heap_create")(1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Stream field heap failed");
            IntPtr descriptor=Fn<Class>(m,"boom_get_class_descriptor")(owner),pool=Fn<GetPool>(m,"boom_get_stream_pool")(owner),table=Marshal.ReadIntPtr(pool,8);
            Check(Marshal.ReadInt32(descriptor,8)==0&&Marshal.ReadIntPtr(pool,16)==IntPtr.Zero,"Stream superclass initialized before active subclass use");
            Check(Fn<GetPool>(m,"boom_get_stream_pool")(uint.MaxValue)==IntPtr.Zero,"Unknown stream class accepted");Metadata(r,pool);
            const int count=2049;long[] args=new long[count*16];for(int i=0;i<count;i++)args[i*16]=unchecked(0x80000000U+(uint)i*65537);
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(args,0,input,args.Length);workers=Fn<PoolCreate>(r,"boom_pool_create")(8);Check(workers!=IntPtr.Zero,"Stream initialization workers failed");
            for(int batch=0;batch<3;batch++) {
                Check(Fn<PoolRun>(r,"boom_pool_run")(workers,GetProcAddress(m,"boom_entry"),input,output,count)==0,"Stream initialization batch failed");
                for(int i=0;i<count;i++)Check(unchecked((uint)Marshal.ReadInt64(output,i*32))==unchecked((uint)args[i*16]+(uint)increment)&&Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0,"Stream initializer changed worker result/context");
                Check(Marshal.ReadInt32(descriptor,8)==2&&Marshal.ReadIntPtr(pool,16)==table&&Marshal.ReadInt64(heap,56)==retained,"Stream superclass initialization/field registration changed");
                if(retained!=0){IntPtr access=Marshal.ReadIntPtr(Fn<Field>(m,"boom_get_static_field")(owner,accessField));Check(access!=IntPtr.Zero&&access==Marshal.ReadIntPtr(Fn<Field>(m,"boom_get_static_field")(sharedOwner,sharedField)),"Output FD_ACCESS differs from the original SharedSecrets registration");}
                IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n);Check(Fn<Collect>(m,"boom_heap_collect")(heap,roots,n)==0&&Marshal.ReadInt64(heap,56)==retained,"Stream initializer roots were not retained");
            }
            // Raw native object fixture; the Java stream constructor is not executed.
            var c=new Context();IntPtr stream=Fn<ObjectNew>(r,"boom_object_new")(heap,Marshal.ReadIntPtr(table,8),ref c);Check(stream!=IntPtr.Zero&&c.Kind==0,"Raw stream layout allocation failed");
            var get=Fn<Descriptor>(r,"boom_stream_descriptor");c=new Context();Check(get(ref c,stream,pool)==IntPtr.Zero&&c.Kind==0,"Empty stream fd field did not read null");
            if(retained!=0) {IntPtr fd=Marshal.ReadIntPtr(Fn<Field>(m,"boom_get_static_field")(fdOwner,outputField));Check(fd!=IntPtr.Zero,"Missing original output descriptor");Marshal.WriteIntPtr(stream,Marshal.ReadInt32(table,16),fd);for(int i=0;i<64;i++){c=new Context();Check(get(ref c,stream,pool)==fd&&c.Kind==0,"Registered stream field did not read the actual descriptor");}}
            c=new Context();get(ref c,IntPtr.Zero,pool);Check(c.Kind==4,"Null stream field lookup status changed");
            c=new Context();IntPtr wrong=Fn<ArrayNew>(r,"boom_array_new")(heap,1,8,ref c);Check(wrong!=IntPtr.Zero&&c.Kind==0,"Raw wrong-type fixture failed");c=new Context();get(ref c,wrong,pool);Check(c.Kind==7,"Wrong-layout stream field lookup accepted");
            Check(Marshal.ReadInt64(heap,56)==retained+2,"Stream field access allocated guest temporaries");
            IntPtr allRoots=Fn<Roots>(m,"boom_get_static_roots")(out uint rootCount);Check(Fn<Collect>(m,"boom_heap_collect")(heap,allRoots,rootCount)==2&&Marshal.ReadInt64(heap,56)==retained,"Raw stream field fixtures leaked");
        } finally {if(workers!=IntPtr.Zero)Fn<PoolDestroy>(r,"boom_pool_destroy")(workers);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Fn<Destroy>(m,"boom_heap_destroy")(heap);FreeLibrary(r);FreeLibrary(m);}
    }
    public static void Failure(string dll,string runtime,uint owner,uint failureOwner,uint initializer,bool output) {
        IntPtr m=Open(dll),r=Open(runtime),heap=IntPtr.Zero;
        try {
            heap=Fn<Create>(m,"boom_heap_create")(4096);Check(heap!=IntPtr.Zero&&Fn<Bind>(m,"boom_bind_heap")(heap)==1,"Stream failure heap failed");
            IntPtr pool=Fn<GetPool>(m,"boom_get_stream_pool")(owner);
            if(output){ulong prefill=checked((ulong)Marshal.ReadInt64(heap,16)-288);Check(Fn<Alloc>(r,"boom_heap_alloc")(heap,prefill,0,1)!=IntPtr.Zero,"Stream failure prefill failed");}
            else {Marshal.WriteIntPtr(pool,16,new IntPtr(1));}
            var entry=Fn<Entry>(m,"boom_entry");var c=new Context();entry(ref c,new ulong[]{123});
            uint expected=output?3U:7U;IntPtr descriptor=Fn<Class>(m,"boom_get_class_descriptor")(owner),target=Fn<Class>(m,"boom_get_class_descriptor")(failureOwner);
            Check(c.Kind==expected&&c.Method==initializer&&c.Depth==0&&Marshal.ReadInt32(descriptor,8)==3&&Marshal.ReadInt32(target,8)==3,"Stream initializer failure lost its original source/state: kind="+c.Kind+", method="+c.Method);
            if(output){Check(Marshal.ReadIntPtr(pool,16)==IntPtr.Zero,"Stream field registration ran after its failed lazy getter");IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n);Check(Fn<Collect>(m,"boom_heap_collect")(heap,roots,n)>0,"Failed stream initializer prefill was not reclaimed");}
            c=new Context();entry(ref c,new ulong[]{123});Check(c.Kind==9&&c.Depth==0&&Marshal.ReadInt32(descriptor,8)==3,"Failed stream initialization was retried");
        } finally {if(heap!=IntPtr.Zero)Fn<Destroy>(m,"boom_heap_destroy")(heap);FreeLibrary(r);FreeLibrary(m);}
    }
}
