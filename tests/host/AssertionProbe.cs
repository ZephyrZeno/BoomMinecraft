// Development host only. Policy validation, queries, class initialization,
// worker execution, allocation and tracing execute in the assembly modules.
using System;
using System.Runtime.InteropServices;
public static class BoomAssertionProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {public uint Kind,PC,Method,Depth;}
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
    static void Check(bool pass,string message){if(!pass)throw new Exception(message);}
    static IntPtr Open(string path){IntPtr p=LoadLibraryExW(path,IntPtr.Zero,0x1100);Check(p!=IntPtr.Zero,"Assertion DLL load failed");return p;}
    static T Fn<T>(IntPtr module,string name){IntPtr p=GetProcAddress(module,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    public static void Abi(string path){
        IntPtr module=Open(path),heap=IntPtr.Zero,data=IntPtr.Zero;
        try{
            heap=Fn<Create>(module,"boom_heap_create")(65536);Check(heap!=IntPtr.Zero,"Assertion ABI heap failed");
            data=Marshal.AllocHGlobal(256);Marshal.Copy(new byte[256],0,data,256);
            IntPtr layout=data,type=IntPtr.Add(data,32),rows=IntPtr.Add(data,80),pool=IntPtr.Add(data,112),roots=IntPtr.Add(data,176),policy=IntPtr.Add(data,184),statuses=IntPtr.Add(data,216),args=IntPtr.Add(data,224);
            Marshal.WriteInt32(layout,0x4f424a43);Marshal.WriteInt32(layout,4,1);Marshal.WriteInt64(layout,8,8);Marshal.WriteInt32(layout,20,1);
            Marshal.WriteInt32(type,0x54595045);Marshal.WriteInt32(type,4,1);Marshal.WriteInt32(type,8,1);Marshal.WriteIntPtr(rows,type);
            Marshal.WriteInt32(pool,0x4d495252);Marshal.WriteInt32(pool,4,2);Marshal.WriteInt32(pool,12,1);
            Marshal.WriteIntPtr(pool,16,roots);Marshal.WriteIntPtr(pool,24,rows);Marshal.WriteIntPtr(pool,32,layout);Marshal.WriteIntPtr(pool,56,policy);
            Marshal.WriteInt32(policy,0x41535354);Marshal.WriteInt32(policy,4,1);Marshal.WriteInt32(policy,8,3);Marshal.WriteInt32(policy,12,1);Marshal.WriteIntPtr(policy,16,statuses);Marshal.WriteInt32(statuses,1);
            var load=Fn<Load>(module,"boom_mirror_load");var invoke=Fn<Intrinsic>(module,"boom_mirror_intrinsic");
            var ctx=new Context();IntPtr mirror=load(heap,pool,0,ref ctx);Check(mirror!=IntPtr.Zero&&ctx.Kind==0,"ABI2 mirror creation failed");Marshal.WriteIntPtr(args,mirror);
            ctx=new Context();Check(invoke(ref ctx,args,pool,7)==1&&ctx.Kind==0,"Stored true assertion status was not read");
            Marshal.WriteInt32(statuses,0);ctx=new Context();Check(invoke(ref ctx,args,pool,7)==0&&ctx.Kind==0,"Stored false assertion status was not read");
            Marshal.WriteInt32(statuses,2);ctx=new Context();Check(invoke(ref ctx,args,pool,7)==0&&ctx.Kind==7,"Nonboolean status accepted");Marshal.WriteInt32(statuses,1);
            foreach(int offset in new[]{0,4,8,12,24}){
                int old=Marshal.ReadInt32(policy,offset);Marshal.WriteInt32(policy,offset,offset==8?4:offset==12?2:offset==0?0:2);
                ctx=new Context();Check(invoke(ref ctx,args,pool,7)==0&&ctx.Kind==7,"Invalid policy header accepted at "+offset);
                ctx=new Context();Check(load(heap,pool,0,ref ctx)==IntPtr.Zero&&ctx.Kind==7,"Cached mirror bypassed policy validation");Marshal.WriteInt32(policy,offset,old);
            }
            Marshal.WriteIntPtr(policy,16,IntPtr.Zero);ctx=new Context();Check(invoke(ref ctx,args,pool,7)==0&&ctx.Kind==7,"Missing statuses accepted");Marshal.WriteIntPtr(policy,16,statuses);
            Marshal.WriteIntPtr(pool,56,IntPtr.Zero);ctx=new Context();Check(invoke(ref ctx,args,pool,7)==0&&ctx.Kind==7,"ABI2 without policy accepted");
            Marshal.WriteInt32(pool,4,1);ctx=new Context();Check(invoke(ref ctx,args,pool,7)==0&&ctx.Kind==7,"Legacy ABI silently accepted assertions");
            ctx=new Context();Check(invoke(ref ctx,args,pool,1)==0&&ctx.Kind==0,"Legacy mirror query regressed");
            Marshal.WriteInt32(pool,4,2);Marshal.WriteIntPtr(pool,56,policy);
            Marshal.WriteIntPtr(args,IntPtr.Zero);ctx=new Context();Check(invoke(ref ctx,args,pool,7)==0&&ctx.Kind==4,"Null assertion query did not report NPE");Marshal.WriteIntPtr(args,mirror);
            ctx=new Context();Check(invoke(ref ctx,args,pool,8)==0&&ctx.Kind==7,"Unknown mirror opcode accepted");
            Check(Fn<Collect>(module,"boom_heap_collect")(heap,roots,1)==0&&Marshal.ReadInt64(heap,56)==1,"Assertion mirror root was collected");
            Marshal.WriteIntPtr(roots,IntPtr.Zero);Check(Fn<Collect>(module,"boom_heap_collect")(heap,roots,1)==1,"Unused assertion mirror was not reclaimable");
        }finally{if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);if(data!=IntPtr.Zero)Marshal.FreeHGlobal(data);FreeLibrary(module);}
    }
    public static void Cold(string dll,string runtime,uint owner,uint field,uint expected){
        IntPtr module=Open(dll),library=IntPtr.Zero,heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try{
            library=Open(runtime);heap=Fn<Create>(module,"boom_heap_create")(1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Cold assertion heap failed");
            const int count=8195;input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(new long[count*16],0,input,count*16);
            pool=Fn<PoolCreate>(library,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Cold assertion pool failed");
            Check(Fn<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)==0,"Cold assertion dispatch failed");
            var results=new long[count*4];Marshal.Copy(output,results,0,results.Length);
            for(int i=0;i<count;i++)Check(unchecked((ulong)results[i*4])==expected&&results[i*4+1]==0&&results[i*4+2]==0&&results[i*4+3]==0,"Cold assertion context/result mismatch");
            IntPtr counter=Fn<Field>(module,"boom_get_static_field")(owner,field);Check(counter!=IntPtr.Zero&&Marshal.ReadInt32(counter)==1,"Assertion initializer executed more than once");
            Check(Marshal.ReadInt64(heap,56)==1,"Assertion mirror allocated more than once");uint rootCount;IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out rootCount);
            Check(Fn<Collect>(module,"boom_heap_collect")(heap,roots,rootCount)==0,"Assertion mirror root lost");var ctx=new Context();
            Check(Fn<Entry>(module,"boom_entry")(ref ctx,new ulong[]{0})==expected&&ctx.Kind==0&&Marshal.ReadInt32(counter)==1,"Assertion status changed after GC");
        }finally{if(pool!=IntPtr.Zero)Fn<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);if(library!=IntPtr.Zero)FreeLibrary(library);FreeLibrary(module);}
    }
}
