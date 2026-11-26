// Development host only. Layers, module lookup, Java Optional, workers and GC execute as MASM.
using System;
using System.Runtime.InteropServices;
public static class BoomLayerProbe {
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
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ModuleLoad(ref Context ctx,IntPtr pool,uint id);
    public static void Abi(string dll) {
        IntPtr library=Open(dll),heap=IntPtr.Zero,other=IntPtr.Zero,data=IntPtr.Zero;
        try {
            heap=Fn<Create>(library,"boom_heap_create")(65536);other=Fn<Create>(library,"boom_heap_create")(65536);Check(heap!=IntPtr.Zero&&other!=IntPtr.Zero,"Layer ABI heaps failed");
            data=Marshal.AllocHGlobal(1024);Marshal.Copy(new byte[1024],0,data,1024);
            IntPtr mirrorLayout=data,moduleLayout=IntPtr.Add(data,32),layerLayout=IntPtr.Add(data,64),stringLayout=IntPtr.Add(data,96),type=IntPtr.Add(data,128),mirrorRows=IntPtr.Add(data,176),mirrorPool=IntPtr.Add(data,208),mirrorRoots=IntPtr.Add(data,272),entries=IntPtr.Add(data,288),baseText=IntPtr.Add(data,320),jfrText=IntPtr.Add(data,352),strings=IntPtr.Add(data,384),stringRoots=IntPtr.Add(data,448),rows=IntPtr.Add(data,480),membership=IntPtr.Add(data,512),roots=IntPtr.Add(data,528),pool=IntPtr.Add(data,560),layers=IntPtr.Add(data,688),layerRoots=IntPtr.Add(data,768),heapCell=IntPtr.Add(data,784),args=IntPtr.Add(data,800),allRoots=IntPtr.Add(data,832);
            foreach(IntPtr layout in new IntPtr[]{mirrorLayout,moduleLayout,layerLayout,stringLayout}) { Marshal.WriteInt32(layout,0x4f424a43);Marshal.WriteInt32(layout,4,1);Marshal.WriteInt64(layout,8,8);Marshal.WriteInt32(layout,20,1); }
            Marshal.WriteInt64(stringLayout,8,16);Marshal.WriteInt32(stringLayout,16,1);Marshal.WriteInt32(stringLayout,20,2);
            Marshal.WriteInt32(type,0x54595045);Marshal.WriteInt32(type,4,1);Marshal.WriteInt32(type,8,1);Marshal.WriteIntPtr(mirrorRows,type);
            Marshal.WriteInt32(mirrorPool,0x4d495252);Marshal.WriteInt32(mirrorPool,4,1);Marshal.WriteInt32(mirrorPool,12,1);Marshal.WriteIntPtr(mirrorPool,16,mirrorRoots);Marshal.WriteIntPtr(mirrorPool,24,mirrorRows);Marshal.WriteIntPtr(mirrorPool,32,mirrorLayout);Marshal.WriteIntPtr(mirrorPool,40,strings);
            for(int i=0;i<9;i++)Marshal.WriteInt16(baseText,i*2,(short)"java.base"[i]);for(int i=0;i<7;i++)Marshal.WriteInt16(jfrText,i*2,(short)"jdk.jfr"[i]);
            Marshal.WriteIntPtr(entries,baseText);Marshal.WriteInt32(entries,8,9);Marshal.WriteIntPtr(entries,16,jfrText);Marshal.WriteInt32(entries,24,7);
            Marshal.WriteInt32(strings,0x53545250);Marshal.WriteInt32(strings,4,2);Marshal.WriteInt32(strings,16,2);Marshal.WriteIntPtr(strings,24,stringRoots);Marshal.WriteIntPtr(strings,32,entries);Marshal.WriteIntPtr(strings,40,stringLayout);
            Marshal.WriteInt32(rows,0);Marshal.WriteInt32(rows,4,1);Marshal.WriteInt32(rows,8,-1);Marshal.WriteInt32(rows,16,1);Marshal.WriteInt32(rows,20,1);
            Marshal.WriteInt32(pool,0x4d4f4455);Marshal.WriteInt32(pool,4,2);Marshal.WriteInt32(pool,12,3);Marshal.WriteIntPtr(pool,16,roots);Marshal.WriteIntPtr(pool,24,rows);Marshal.WriteIntPtr(pool,32,moduleLayout);Marshal.WriteIntPtr(pool,40,strings);Marshal.WriteIntPtr(pool,56,mirrorPool);Marshal.WriteInt32(pool,64,1);Marshal.WriteIntPtr(pool,72,membership);Marshal.WriteIntPtr(pool,80,layers);Marshal.WriteIntPtr(pool,88,heapCell);
            Marshal.WriteInt32(layers,0x4c415952);Marshal.WriteInt32(layers,4,1);Marshal.WriteInt32(layers,12,2);Marshal.WriteIntPtr(layers,16,layerRoots);Marshal.WriteIntPtr(layers,24,layerLayout);Marshal.WriteIntPtr(layers,32,pool);Marshal.WriteIntPtr(layers,40,heapCell);Marshal.WriteIntPtr(heapCell,heap);
            var invoke=Fn<Intrinsic>(library,"boom_layer_intrinsic");var ctx=new Context();ulong boot=invoke(ref ctx,args,pool,4),empty=invoke(ref ctx,args,pool,5);Check(boot!=0&&empty!=0&&boot!=empty&&ctx.Kind==0,"Layer canonical objects failed");
            Check(invoke(ref ctx,args,pool,4)==boot&&invoke(ref ctx,args,pool,5)==empty&&ctx.Kind==0,"Layer identities changed");
            IntPtr name=Fn<Load>(library,"boom_string_load")(heap,strings,0,ref ctx);Check(name!=IntPtr.Zero&&ctx.Kind==0,"Layer name String failed");
            Marshal.WriteIntPtr(args,new IntPtr(unchecked((long)boot)));Marshal.WriteIntPtr(args,8,name);ulong module=invoke(ref ctx,args,pool,6);Check(module!=0&&ctx.Kind==0,"Layer lookup failed before mirror creation");
            Marshal.WriteIntPtr(args,new IntPtr(unchecked((long)module)));Check(invoke(ref ctx,args,pool,3)==boot&&ctx.Kind==0,"Found module has wrong layer");Check(Marshal.ReadIntPtr(mirrorPool,48)==IntPtr.Zero,"Lookup unexpectedly created a Class mirror");
            IntPtr jfr=Fn<Load>(library,"boom_string_load")(heap,strings,1,ref ctx);Marshal.WriteIntPtr(args,new IntPtr(unchecked((long)boot)));Marshal.WriteIntPtr(args,8,jfr);Check(invoke(ref ctx,args,pool,6)!=0&&ctx.Kind==0,"Second boot module lookup failed");
            ulong unnamed=unchecked((ulong)Fn<ModuleLoad>(library,"boom_module_load")(ref ctx,pool,1).ToInt64());Marshal.WriteIntPtr(args,new IntPtr(unchecked((long)unnamed)));Check(unnamed!=0&&invoke(ref ctx,args,pool,3)==0&&ctx.Kind==0,"Unnamed module acquired a layer");
            Marshal.WriteIntPtr(args,new IntPtr(unchecked((long)empty)));Marshal.WriteIntPtr(args,8,name);Check(invoke(ref ctx,args,pool,6)==0&&ctx.Kind==0,"Empty layer found a module");Marshal.WriteIntPtr(args,8,IntPtr.Zero);ctx=new Context();Check(invoke(ref ctx,args,pool,6)==0&&ctx.Kind==4,"Empty layer ignored null name");
            Marshal.WriteIntPtr(args,IntPtr.Zero);Marshal.WriteIntPtr(args,8,name);ctx=new Context();Check(invoke(ref ctx,args,pool,6)==0&&ctx.Kind==4,"Null layer did not report NPE");ctx=new Context();Check(invoke(ref ctx,args,pool,3)==0&&ctx.Kind==4,"Null module did not report NPE");
            foreach(int offset in new int[]{0,4,12,56}) { int old=Marshal.ReadInt32(layers,offset);Marshal.WriteInt32(layers,offset,123);ctx=new Context();Check(invoke(ref ctx,args,pool,4)==0&&ctx.Kind==7,"Cached layer bypassed descriptor validation");Marshal.WriteInt32(layers,offset,old); }
            Marshal.WriteIntPtr(heapCell,other);ctx=new Context();Check(invoke(ref ctx,args,pool,4)==0&&ctx.Kind==7,"Layer rebound to another heap");Marshal.WriteIntPtr(heapCell,heap);
            Marshal.WriteInt32(pool,4,1);ctx=new Context();Check(invoke(ref ctx,args,pool,4)==0&&ctx.Kind==7,"Legacy module pool accepted layer query");Marshal.WriteInt32(pool,4,2);
            ctx=new Context();IntPtr mirror=Fn<Load>(library,"boom_mirror_load")(heap,mirrorPool,0,ref ctx);Check(mirror!=IntPtr.Zero&&ctx.Kind==0,"Layer ABI mirror failed");Marshal.WriteIntPtr(args,mirror);ctx=new Context();Check(invoke(ref ctx,args,pool,6)==0&&ctx.Kind==7,"Class mirror accepted as layer");
            Marshal.WriteIntPtr(args,new IntPtr(unchecked((long)module)));ctx=new Context();Check(invoke(ref ctx,args,pool,6)==0&&ctx.Kind==7,"Module accepted as layer");Marshal.WriteIntPtr(args,new IntPtr(unchecked((long)boot)));ctx=new Context();Check(invoke(ref ctx,args,pool,3)==0&&ctx.Kind==7,"Layer accepted as module");ctx=new Context();Check(invoke(ref ctx,args,pool,7)==0&&ctx.Kind==7,"Unknown layer opcode accepted");
            int root=0;foreach(IntPtr area in new IntPtr[]{mirrorRoots,stringRoots,roots,layerRoots}) { int count=area==mirrorRoots?1:area==roots?3:2;for(int i=0;i<count;i++)Marshal.WriteIntPtr(allRoots,(root++)*8,Marshal.ReadIntPtr(area,i*8)); }
            Check(Marshal.ReadInt64(heap,56)==10&&Fn<Collect>(library,"boom_heap_collect")(heap,allRoots,8)==0,"Layer/module/name roots were lost");Check(Fn<Collect>(library,"boom_heap_collect")(heap,IntPtr.Zero,0)==10,"Layer objects not reclaimable after test-only root removal");
        } finally { if(heap!=IntPtr.Zero)Fn<Destroy>(library,"boom_heap_destroy")(heap);if(other!=IntPtr.Zero)Fn<Destroy>(library,"boom_heap_destroy")(other);if(data!=IntPtr.Zero)Marshal.FreeHGlobal(data);FreeLibrary(library); }
    }
    public static void Cold(string dll,string runtime,uint owner,uint field) {
        IntPtr module=Open(dll),library=IntPtr.Zero,heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try {
            library=Open(runtime);heap=Fn<Create>(module,"boom_heap_create")(16*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Layer cold heap failed");
            const int count=8195;input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(new long[count*16],0,input,count*16);pool=Fn<PoolCreate>(library,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Layer cold pool failed");
            Check(Fn<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)==0,"Layer cold run failed");var results=new long[count*4];Marshal.Copy(output,results,0,results.Length);
            for(int i=0;i<count;i++)Check(results[i*4]==17&&results[i*4+1]==0&&results[i*4+2]==0&&results[i*4+3]==0,"Cold layer result/context mismatch");
            IntPtr counter=Fn<Field>(module,"boom_get_static_field")(owner,field);Check(counter!=IntPtr.Zero&&Marshal.ReadInt32(counter)==1,"Layer initializer ran more than once");Check(Marshal.ReadInt64(heap,56)==8,"Cold layer allocation count mismatch");uint countRoots;IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out countRoots);
            Check(Fn<Collect>(module,"boom_heap_collect")(heap,roots,countRoots)==1&&Marshal.ReadInt64(heap,56)==7,"Layer cold roots or temporary Optional reclamation failed");var ctx=new Context();Check(Fn<Entry>(module,"boom_entry")(ref ctx,new ulong[]{0})==17&&ctx.Kind==0&&Marshal.ReadInt32(counter)==1,"Cached layer changed after GC");
        } finally { if(pool!=IntPtr.Zero)Fn<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);if(library!=IntPtr.Zero)FreeLibrary(library);FreeLibrary(module); }
    }
    public static void Parallel(string dll,string runtime,int[] membership,bool direct) {
        IntPtr module=Open(dll),library=IntPtr.Zero,heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try {
            library=Open(runtime);heap=Fn<Create>(module,"boom_heap_create")(16*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Layer parallel heap failed");
            const int count=8195;input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);var values=new long[count*16];long temporaries=0,memberCount=0;
            foreach(int value in membership)memberCount+=value;
            for(int i=0;i<count;i++){values[i*16]=direct?i:i%membership.Length;if(!direct)temporaries+=membership[i%membership.Length];}Marshal.Copy(values,0,input,values.Length);pool=Fn<PoolCreate>(library,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Layer parallel pool failed");
            long rooted=direct?2:2+memberCount+membership.Length*2;
            for(int batch=0;batch<2;batch++) {
                Check(Fn<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)==0,"Layer parallel dispatch failed");var results=new long[count*4];Marshal.Copy(output,results,0,results.Length);
                for(int i=0;i<count;i++){long expected=direct?(i%2==0?1:0):membership[i%membership.Length];Check(results[i*4]==expected&&results[i*4+1]==0&&results[i*4+2]==0&&results[i*4+3]==0,"Layer parallel result/context mismatch");}
                Check(Marshal.ReadInt64(heap,56)==rooted+temporaries,"Duplicate layer/module/String/EMPTY allocation or missing Optional");uint countRoots;IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out countRoots);
                Check(Fn<Collect>(module,"boom_heap_collect")(heap,roots,countRoots)==(ulong)temporaries&&Marshal.ReadInt64(heap,56)==rooted,"Layer parallel root graph or Optional reclamation failed");
            }
        } finally { if(pool!=IntPtr.Zero)Fn<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);if(library!=IntPtr.Zero)FreeLibrary(library);FreeLibrary(module); }
    }
}
