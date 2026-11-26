// Development orchestration only. Module identity, initialization, workers and GC are MASM.
using System;
using System.Runtime.InteropServices;
public static class BoomModuleProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Load(IntPtr heap,IntPtr pool,uint id,ref Context ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Intrinsic(ref Context ctx,IntPtr args,IntPtr pool,uint op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(uint owner,uint index);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context ctx,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int PoolRun(IntPtr pool,IntPtr entry,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int PoolDestroy(IntPtr pool);
    static void Check(bool pass,string message) { if(!pass)throw new Exception(message); }
    static IntPtr Open(string path) { IntPtr p=LoadLibraryExW(path,IntPtr.Zero,0x1100);Check(p!=IntPtr.Zero,"Module DLL load failed");return p; }
    static T Fn<T>(IntPtr module,string name) { IntPtr p=GetProcAddress(module,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p); }
    public static void Abi(string dll) {
        IntPtr library=Open(dll),heap=IntPtr.Zero,other=IntPtr.Zero,data=IntPtr.Zero;
        try {
            heap=Fn<Create>(library,"boom_heap_create")(65536);other=Fn<Create>(library,"boom_heap_create")(65536);Check(heap!=IntPtr.Zero&&other!=IntPtr.Zero,"Module ABI heaps failed");
            data=Marshal.AllocHGlobal(640);Marshal.Copy(new byte[640],0,data,640);
            IntPtr mirrorLayout=data,moduleLayout=IntPtr.Add(data,32),type=IntPtr.Add(data,64),mirrorRows=IntPtr.Add(data,128),mirrorPool=IntPtr.Add(data,192),mirrorRoots=IntPtr.Add(data,256),strings=IntPtr.Add(data,280),rows=IntPtr.Add(data,384),membership=IntPtr.Add(data,400),pool=IntPtr.Add(data,416),roots=IntPtr.Add(data,512),args=IntPtr.Add(data,544),allRoots=IntPtr.Add(data,568);
            foreach(IntPtr layout in new IntPtr[]{mirrorLayout,moduleLayout}) { Marshal.WriteInt32(layout,0x4f424a43);Marshal.WriteInt32(layout,4,1);Marshal.WriteInt64(layout,8,8);Marshal.WriteInt32(layout,20,1); }
            Marshal.WriteInt32(type,0x54595045);Marshal.WriteInt32(type,4,1);Marshal.WriteInt32(type,8,1);
            Marshal.WriteIntPtr(mirrorRows,type);Marshal.WriteIntPtr(mirrorRows,24,type);
            Marshal.WriteInt32(mirrorPool,0x4d495252);Marshal.WriteInt32(mirrorPool,4,1);Marshal.WriteInt32(mirrorPool,12,2);Marshal.WriteIntPtr(mirrorPool,16,mirrorRoots);Marshal.WriteIntPtr(mirrorPool,24,mirrorRows);Marshal.WriteIntPtr(mirrorPool,32,mirrorLayout);Marshal.WriteIntPtr(mirrorPool,40,strings);
            Marshal.WriteInt32(rows,0);Marshal.WriteInt32(rows,4,1);Marshal.WriteInt32(rows,8,-1);Marshal.WriteInt32(membership,4,1);
            Marshal.WriteInt32(pool,0x4d4f4455);Marshal.WriteInt32(pool,4,1);Marshal.WriteInt32(pool,12,2);Marshal.WriteIntPtr(pool,16,roots);Marshal.WriteIntPtr(pool,24,rows);Marshal.WriteIntPtr(pool,32,moduleLayout);Marshal.WriteIntPtr(pool,40,strings);Marshal.WriteIntPtr(pool,56,mirrorPool);Marshal.WriteInt32(pool,64,2);Marshal.WriteIntPtr(pool,72,membership);
            var load=Fn<Load>(library,"boom_mirror_load");var invoke=Fn<Intrinsic>(library,"boom_module_intrinsic");var ctx=new Context();
            IntPtr m0=load(heap,mirrorPool,0,ref ctx),m1=load(heap,mirrorPool,1,ref ctx);Check(ctx.Kind==0&&m0!=IntPtr.Zero&&m1!=IntPtr.Zero,"Module ABI mirrors failed");
            Marshal.WriteIntPtr(args,m0);ulong named=invoke(ref ctx,args,pool,0);Check(named!=0&&ctx.Kind==0,"Named module creation failed");
            Check(invoke(ref ctx,args,pool,0)==named&&ctx.Kind==0,"Named module identity changed");
            Marshal.WriteIntPtr(args,new IntPtr(unchecked((long)named)));Check(invoke(ref ctx,args,pool,2)==1&&ctx.Kind==0,"Named module flag failed");
            Marshal.WriteIntPtr(args,m1);ulong unnamed=invoke(ref ctx,args,pool,0);Check(unnamed!=0&&unnamed!=named&&ctx.Kind==0,"Unnamed module identity failed");
            Marshal.WriteIntPtr(args,new IntPtr(unchecked((long)unnamed)));Check(invoke(ref ctx,args,pool,2)==0&&ctx.Kind==0&&invoke(ref ctx,args,pool,1)==0&&ctx.Kind==0,"Unnamed module queries failed");
            for(uint op=0;op<3;op++) { Marshal.WriteIntPtr(args,IntPtr.Zero);ctx=new Context();Check(invoke(ref ctx,args,pool,op)==0&&ctx.Kind==4,"Null module/class did not report NPE"); }
            Marshal.WriteIntPtr(args,m0);
            foreach(int offset in new int[]{0,4,12,64,68}) {
                int previous=Marshal.ReadInt32(pool,offset);Marshal.WriteInt32(pool,offset,0x12345678);ctx=new Context();Check(invoke(ref ctx,args,pool,0)==0&&ctx.Kind==7,"Cached module bypassed pool validation");Marshal.WriteInt32(pool,offset,previous);
            }
            Marshal.WriteInt32(membership,2);ctx=new Context();Check(invoke(ref ctx,args,pool,0)==0&&ctx.Kind==7,"Out-of-range membership accepted");Marshal.WriteInt32(membership,0);
            Marshal.WriteInt32(rows,4,2);ctx=new Context();Check(invoke(ref ctx,args,pool,0)==0&&ctx.Kind==7,"Malformed named flag accepted");Marshal.WriteInt32(rows,4,1);
            Marshal.WriteIntPtr(pool,48,other);ctx=new Context();Check(invoke(ref ctx,args,pool,0)==0&&ctx.Kind==7,"Module rebound to another heap");Marshal.WriteIntPtr(pool,48,heap);
            Marshal.WriteIntPtr(args,m0);ctx=new Context();Check(invoke(ref ctx,args,pool,2)==0&&ctx.Kind==7,"Class mirror accepted as Module");
            Marshal.WriteIntPtr(args,new IntPtr(unchecked((long)named)));ctx=new Context();Check(invoke(ref ctx,args,pool,0)==0&&ctx.Kind==7,"Module accepted as Class mirror");
            ctx=new Context();Check(invoke(ref ctx,args,pool,3)==0&&ctx.Kind==7,"Unknown module opcode accepted");
            for(int i=0;i<2;i++) { Marshal.WriteIntPtr(allRoots,i*8,Marshal.ReadIntPtr(mirrorRoots,i*8));Marshal.WriteIntPtr(allRoots,16+i*8,Marshal.ReadIntPtr(roots,i*8)); }
            Check(Marshal.ReadInt64(heap,56)==4&&Fn<Collect>(library,"boom_heap_collect")(heap,allRoots,4)==0,"Module/mirror roots were lost");
            Check(Fn<Collect>(library,"boom_heap_collect")(heap,IntPtr.Zero,0)==4&&Marshal.ReadInt64(heap,48)==0,"Module heap failed full reclamation after test-only root removal");
        } finally { if(heap!=IntPtr.Zero)Fn<Destroy>(library,"boom_heap_destroy")(heap);if(other!=IntPtr.Zero)Fn<Destroy>(library,"boom_heap_destroy")(other);if(data!=IntPtr.Zero)Marshal.FreeHGlobal(data);FreeLibrary(library); }
    }
    public static void Cold(string dll,string runtime,uint owner,uint field) {
        IntPtr module=Open(dll),library=IntPtr.Zero,heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try {
            library=Open(runtime);heap=Fn<Create>(module,"boom_heap_create")(1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Cold module heap failed");
            const int count=8195;input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(new long[count*16],0,input,count*16);
            pool=Fn<PoolCreate>(library,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Cold module workers failed");
            Check(Fn<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)==0,"Cold module dispatch failed");
            var results=new long[count*4];Marshal.Copy(output,results,0,results.Length);
            for(int i=0;i<count;i++)Check(results[i*4]==11&&results[i*4+1]==0&&results[i*4+2]==0&&results[i*4+3]==0,"Cold module context/result mismatch");
            IntPtr counter=Fn<Field>(module,"boom_get_static_field")(owner,field);Check(counter!=IntPtr.Zero&&Marshal.ReadInt32(counter)==1,"Module query initializer ran more than once");
            Check(Marshal.ReadInt64(heap,56)==4,"Expected exactly two module identities and two Class mirrors");uint rootCount;IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out rootCount);
            Check(Fn<Collect>(module,"boom_heap_collect")(heap,roots,rootCount)==0,"Module identity root lost");var ctx=new Context();
            Check(Fn<Entry>(module,"boom_entry")(ref ctx,new ulong[]{0})==11&&ctx.Kind==0&&Marshal.ReadInt32(counter)==1,"Module identity changed after GC");
        } finally { if(pool!=IntPtr.Zero)Fn<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);if(library!=IntPtr.Zero)FreeLibrary(library);FreeLibrary(module); }
    }
    public static void Race(string dll,string runtime) {
        IntPtr module=Open(dll),library=IntPtr.Zero,heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try {
            library=Open(runtime);heap=Fn<Create>(module,"boom_heap_create")(1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Module race heap failed");
            const int count=8195;input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);var values=new long[count*16];for(int i=0;i<count;i++)values[i*16]=i&15;Marshal.Copy(values,0,input,values.Length);
            pool=Fn<PoolCreate>(library,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Module race workers failed");
            for(int batch=0;batch<2;batch++) {
                Check(Fn<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)==0,"Module race dispatch failed");
                var results=new long[count*4];Marshal.Copy(output,results,0,results.Length);
                for(int i=0;i<count;i++) { int selector=i&15;long expected=selector<=3||selector==9?0:1;Check(results[i*4]==expected&&results[i*4+1]==0&&results[i*4+2]==0&&results[i*4+3]==0,"Concurrent module membership mismatch"); }
                // No shared Java initializer serializes these queries: both module
                // identities and all selected Class mirrors are cold in batch 0.
                Check(Marshal.ReadInt64(heap,56)==19,"Duplicate concurrent module/mirror allocation");uint rootCount;IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out rootCount);
                Check(Fn<Collect>(module,"boom_heap_collect")(heap,roots,rootCount)==0,"Concurrent module identities lost after quiescent GC");
            }
        } finally { if(pool!=IntPtr.Zero)Fn<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);if(library!=IntPtr.Zero)FreeLibrary(library);FreeLibrary(module); }
    }
}
