// Test orchestration only. The monitor, heap, compiled Java and worker pool are MASM.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
public static class BoomMonitorProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string path,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr heap,ulong bytes,uint refs,ulong type);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Monitor(IntPtr heap,IntPtr obj,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context context,[In] ulong[] argv);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int PoolRun(IntPtr pool,IntPtr entry,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int PoolDestroy(IntPtr pool);
    static void Check(bool value,string message) { if(!value)throw new Exception(message); }
    static IntPtr Open(string path) { IntPtr m=LoadLibraryExW(path,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Monitor DLL load failed");return m; }
    static T Fn<T>(IntPtr module,string name) { IntPtr p=GetProcAddress(module,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p); }
    public static void Abi(string runtime) {
        IntPtr module=Open(runtime),heap=IntPtr.Zero,roots=IntPtr.Zero;bool finished=false;
        try {
            heap=Fn<Create>(module,"boom_heap_create")(65536);Check(heap!=IntPtr.Zero,"Monitor heap creation failed");
            var alloc=Fn<Alloc>(module,"boom_heap_alloc");var enter=Fn<Monitor>(module,"boom_monitor_enter");var exit=Fn<Monitor>(module,"boom_monitor_exit");var collect=Fn<Collect>(module,"boom_heap_collect");
            IntPtr a=alloc(heap,8,0,1),b=alloc(heap,0,0,1);Check(a!=IntPtr.Zero&&b!=IntPtr.Zero,"Monitor objects failed");
            var ctx=new Context();Check(enter(heap,a,ref ctx)==0&&enter(heap,a,ref ctx)==0&&Marshal.ReadInt64(heap,112)==2,"Monitor recursion failed");
            Check(collect(heap,IntPtr.Zero,0)==ulong.MaxValue&&Fn<Destroy>(module,"boom_heap_destroy")(heap)==0,"Active monitor was collected/destroyed");
            var other=Task.Run(()=>{var c=new Context();return exit(heap,a,ref c)==17&&c.Kind==17;});Check(other.Wait(5000)&&other.Result,"Foreign monitor exit accepted");
            var independent=Task.Run(()=>{var c=new Context();return enter(heap,b,ref c)==0&&exit(heap,b,ref c)==0;});Check(independent.Wait(5000)&&independent.Result,"Distinct objects shared a monitor");
            ctx.Kind=1;ctx.PC=23;ctx.Method=77;Check(exit(heap,a,ref ctx)==0&&ctx.Kind==1&&ctx.PC==23&&ctx.Method==77,"Exceptional monitor exit overwrote pending exception");
            Check(exit(heap,a,ref ctx)==0&&Marshal.ReadInt64(heap,112)==0,"Recursive monitor was not fully released");
            ctx=new Context();Check(exit(heap,a,ref ctx)==17&&ctx.Kind==17,"Unowned monitor exit accepted");
            ctx=new Context();Check(enter(heap,IntPtr.Zero,ref ctx)==4&&ctx.Kind==4,"Null monitor enter accepted");
            ctx=new Context();Check(exit(heap,IntPtr.Zero,ref ctx)==4&&ctx.Kind==4,"Null monitor exit accepted");
            Marshal.WriteInt32(heap,108,0);ctx=new Context();Check(enter(heap,a,ref ctx)==7,"Old heap without monitor capability accepted");Marshal.WriteInt32(heap,108,1);
            for(int i=0;i<10000;i++){ctx=new Context();Check(enter(heap,a,ref ctx)==0&&exit(heap,a,ref ctx)==0,"Monitor node reuse failed");}
            Check(Marshal.ReadInt64(heap,56)==4,"Monitor metadata grew with repeated acquisitions"); // two Java objects + two reusable nodes from nested independent locks
            var start=new ManualResetEventSlim(false);var tasks=new Task[8];
            for(int t=0;t<tasks.Length;t++)tasks[t]=Task.Run(()=>{start.Wait();for(int n=0;n<1024;n++){var c=new Context();Check(enter(heap,a,ref c)==0,"Contended enter failed");int value=Marshal.ReadInt32(a);Marshal.WriteInt32(a,value+1);Check(exit(heap,a,ref c)==0,"Contended exit failed");}});
            start.Set();Check(Task.WaitAll(tasks,30000),"Monitor contention timed out");Check(Marshal.ReadInt32(a)==8192&&Marshal.ReadInt64(heap,112)==0,"Contended monitor lost writes or ownership");
            roots=Marshal.AllocHGlobal(16);Marshal.WriteIntPtr(roots,a);Marshal.WriteIntPtr(roots,8,b);
            Check(collect(heap,roots,2)!=ulong.MaxValue&&Marshal.ReadInt64(heap,56)==2&&Marshal.ReadInt64(heap,96)==0&&Marshal.ReadInt64(heap,120)==0,"Idle monitor records or keys survived collection");
            Check(collect(heap,IntPtr.Zero,0)==2,"Monitor registry retained Java objects");
            // A zero-payload object can legally have its data pointer at the end of the arena.
            IntPtr small=Fn<Create>(module,"boom_heap_create")(4096);Check(small!=IntPtr.Zero,"Small monitor heap failed");
            try { IntPtr last=alloc(small,unchecked((ulong)(Marshal.ReadInt64(small,16)-64)),0,1);IntPtr end=alloc(small,0,0,1);Check(last!=IntPtr.Zero&&end==Marshal.ReadIntPtr(small,24),"Arena-end fixture failed");ctx=new Context();Check(enter(small,end,ref ctx)==3&&ctx.Kind==3,"Monitor metadata ignored budget/OOM at arena end");Check(Marshal.ReadInt64(small,112)==0&&Marshal.ReadInt32(small,104)==0,"Monitor OOM leaked ownership"); } finally { Check(Fn<Destroy>(module,"boom_heap_destroy")(small)==1,"Small monitor heap destroy failed"); }
            finished=true;
        } finally { if(roots!=IntPtr.Zero)Marshal.FreeHGlobal(roots);if(heap!=IntPtr.Zero&&Marshal.ReadInt64(heap,112)==0)Fn<Destroy>(module,"boom_heap_destroy")(heap);if(finished)FreeLibrary(module); }
    }
    public static void Parallel(string dll,string runtime) {
        IntPtr module=Open(dll),library=Open(runtime),heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try {
            heap=Fn<Create>(module,"boom_heap_create")(16*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Synchronized program binding failed");
            pool=Fn<PoolCreate>(library,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Monitor workers failed");
            const int count=8195;input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(new long[count*16],0,input,count*16);
            long retained=-1;
            for(int batch=0;batch<3;batch++) {
                Check(Fn<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)==0,"Synchronized worker dispatch failed");
                var found=new bool[count];
                for(int i=0;i<count;i++){int n=unchecked((int)Marshal.ReadInt64(output,i*32))-batch*count-1;Check(n>=0&&n<count&&!found[n]&&Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0,"Synchronized update mismatch: "+dll+" batch="+batch+" index="+i+" result="+Marshal.ReadInt64(output,i*32)+" context="+Marshal.ReadInt64(output,i*32+8)+","+Marshal.ReadInt64(output,i*32+16)+","+Marshal.ReadInt64(output,i*32+24)+" active="+Marshal.ReadInt64(heap,112));found[n]=true;}
                Check(Marshal.ReadInt64(heap,112)==0,"Synchronized method leaked held/waiting monitor");
                IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out uint rootCount);Check(Fn<Collect>(module,"boom_heap_collect")(heap,roots,rootCount)!=ulong.MaxValue,"Monitor post-batch GC failed");
                long live=Marshal.ReadInt64(heap,56);Check(live>0&&(retained<0||retained==live),"Monitor registry leaked nodes after GC");retained=live;
            }
        } finally { if(pool!=IntPtr.Zero)Fn<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);FreeLibrary(library);FreeLibrary(module); }
    }
    public static void ClassLock(string dll,uint typeId) {
        IntPtr module=Open(dll),heap=IntPtr.Zero;bool finished=false;
        try {
            heap=Fn<Create>(module,"boom_heap_create")(65536);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Class monitor heap failed");
            var entry=Fn<Entry>(module,"boom_entry");var enter=Fn<Monitor>(module,"boom_monitor_enter");var exit=Fn<Monitor>(module,"boom_monitor_exit");var ctx=new Context();
            Check(entry(ref ctx,new ulong[]{0})==1&&ctx.Kind==0,"Class monitor first invocation failed");
            IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out uint count),mirror=IntPtr.Zero;
            // Mirror ABI1/2 stores the metadata type ID in an 8-byte payload.
            for(int i=0;i<count;i++){IntPtr obj=Marshal.ReadIntPtr(roots,i*8);if(obj!=IntPtr.Zero&&Marshal.ReadInt64(obj,-16)==8&&Marshal.ReadInt64(obj)==typeId){mirror=obj;break;}}
            Check(mirror!=IntPtr.Zero,"Static method did not use its actual Class mirror");ctx=new Context();Check(enter(heap,mirror,ref ctx)==0,"External Class monitor enter failed");
            Check(entry(ref ctx,new ulong[]{0})==2&&ctx.Kind==0&&Marshal.ReadInt64(heap,112)==1,"Static method failed Class mirror recursion");
            var started=new ManualResetEventSlim(false);var task=Task.Run(()=>{started.Set();var c=new Context();return entry(ref c,new ulong[]{0})==3&&c.Kind==0;});
            Check(started.Wait(5000)&&!task.Wait(100),"Static method ignored its Class monitor");ctx=new Context();Check(exit(heap,mirror,ref ctx)==0,"Class monitor release failed");Check(task.Wait(5000)&&task.Result,"Class monitor waiter failed");
            Check(Marshal.ReadInt64(heap,112)==0,"Class monitor waiter leaked ownership");finished=true;
        }finally {if(heap!=IntPtr.Zero&&Marshal.ReadInt64(heap,112)==0)Fn<Destroy>(module,"boom_heap_destroy")(heap);if(finished)FreeLibrary(module);}
    }
}
