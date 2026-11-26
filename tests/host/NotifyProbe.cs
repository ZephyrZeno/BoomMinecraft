// Disposable CLI controller for generated notification calls and assembly monitor ownership.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomNotifyProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context{public uint Kind,PC,Method,Depth;public ulong Pending,Plan;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)]static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")]static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Indexed(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Field(uint owner,uint field);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Load(IntPtr heap,IntPtr pool,uint id,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Entry(ref Context c,[In]ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Service(ref Context c,[In]ulong[] a,IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate uint Release();
    static void Check(bool v,string why){if(!v)throw new Exception(why);}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static ulong Bits(IntPtr p){return unchecked((ulong)p.ToInt64());}
    static void GC(IntPtr m,IntPtr heap,params IntPtr[] extra){IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n),all=Marshal.AllocHGlobal(checked(((int)n+extra.Length)*8));try{for(int i=0;i<n;i++)Marshal.WriteIntPtr(all,i*8,Marshal.ReadIntPtr(roots,i*8));for(int i=0;i<extra.Length;i++)Marshal.WriteIntPtr(all,((int)n+i)*8,extra[i]);Check(Fn<Collect>(m,"boom_heap_collect")(heap,all,n+(uint)extra.Length)!=ulong.MaxValue,"Reflection root collection failed");}finally{Marshal.FreeHGlobal(all);}}

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate uint Monitor(IntPtr heap,IntPtr value,ref Context c);

    public static void Failure(string dll,uint illegalClass,uint nullClass,uint method){
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),heap=IntPtr.Zero;Check(m!=IntPtr.Zero,"Uncaught notification DLL load failed");try{heap=Fn<Create>(m,"boom_heap_create")(1048576);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Uncaught notification heap bind failed");IntPtr value=Fn<Alloc>(m,"boom_heap_alloc")(heap,16,0,267);var entry=Fn<Entry>(m,"boom_entry32");var layout=Fn<Indexed>(m,"boom_get_object_layout");foreach(bool nil in new[]{false,true}){var c=new Context();Check(entry(ref c,new[]{nil?0UL:Bits(value)})==IntPtr.Zero&&c.Kind==16&&c.Pending!=0&&c.PC==1&&c.Method==method&&c.Depth==0,"Uncaught notification source location changed");IntPtr error=new IntPtr(unchecked((long)c.Pending));Check(Marshal.ReadIntPtr(error,-8)==layout(nil?nullClass:illegalClass),"Uncaught notification Throwable type differs: nil="+nil+" kind="+c.Kind+" class="+(nil?nullClass:illegalClass));GC(m,heap,value,error);}}finally{if(m!=IntPtr.Zero)Check(Fn<Release>(m,"boom_release_trace_pool")()==0,"Uncaught notification Java frames remain");if(heap!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(heap);if(m!=IntPtr.Zero)FreeLibrary(m);}}
    public static int[] Run(string dll,string runtime=null){
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),r=IntPtr.Zero,heap=IntPtr.Zero,foreign=IntPtr.Zero;Check(m!=IntPtr.Zero,"Notification image load failed");
        try{
            if(runtime!=null){r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100);Check(r!=IntPtr.Zero,"Notification full runtime load failed");}
            IntPtr api=r==IntPtr.Zero?m:r;var create=Fn<Create>(m,"boom_heap_create");var alloc=Fn<Alloc>(m,"boom_heap_alloc");heap=create(8388608);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Notification heap bind failed");
            var entry=Fn<Entry>(m,"boom_entry32");var results=new int[13];for(int i=-1;i<12;i++){var c=new Context();IntPtr v=entry(ref c,new[]{unchecked((ulong)(uint)i)});Check(c.Kind==0&&c.Pending==0&&c.Depth==0,"Generated notify/catch/monitor exit failed: "+i+"/"+c.Kind);results[i+1]=unchecked((int)v.ToInt64());}
            System.Threading.Tasks.Parallel.For(0,8,new System.Threading.Tasks.ParallelOptions{MaxDegreeOfParallelism=8},worker=>{for(int j=0;j<128;j++){int i=(worker*128+j)%13-1;var c=new Context();int v=unchecked((int)entry(ref c,new[]{unchecked((ulong)(uint)i)}).ToInt64());Check(c.Kind==0&&c.Depth==0&&v==results[i+1],"Concurrent generated notification differs");}});
            GC(m,heap);Monitor enter=Fn<Monitor>(api,"boom_monitor_enter"),leave=Fn<Monitor>(api,"boom_monitor_exit"),notify=Fn<Monitor>(api,"boom_monitor_notify"),all=Fn<Monitor>(api,"boom_monitor_notify_all");IntPtr value=alloc(heap,16,0,267);Check(value!=IntPtr.Zero,"Notification object fixture OOM");
            foreach(var send in new[]{notify,all}){
                var c=new Context();Check(send(heap,IntPtr.Zero,ref c)==4&&c.Kind==4,"Null notification differs");c=new Context();Check(send(heap,value,ref c)==17&&c.Kind==17,"Unowned notification accepted");
                c=new Context{Kind=23,PC=91,Method=37,Depth=2,Pending=0x1234,Plan=0x5678};Check(send(IntPtr.Zero,IntPtr.Zero,ref c)==23&&c.Kind==23&&c.PC==91&&c.Method==37&&c.Depth==2&&c.Pending==0x1234&&c.Plan==0x5678,"Pending notification context changed");
            }
            foreign=create(4096);IntPtr wrong=alloc(foreign,16,0,267);var raw=new Context();Check(all(heap,wrong,ref raw)==7&&raw.Kind==7,"Foreign notification object accepted");
            raw=new Context();Check(enter(heap,value,ref raw)==0&&enter(heap,value,ref raw)==0,"Recursive notification monitor enter failed");IntPtr node=Marshal.ReadIntPtr(heap,96);while(node!=IntPtr.Zero&&Marshal.ReadIntPtr(node)!=value)node=Marshal.ReadIntPtr(node,8);Check(node!=IntPtr.Zero&&Marshal.ReadInt32(node,20)==2,"Recursive owner node absent");long leases=Marshal.ReadInt64(heap,112),objects=Marshal.ReadInt64(heap,56);raw=new Context();Check(notify(heap,value,ref raw)==0&&all(heap,value,ref raw)==0&&raw.Kind==0&&Marshal.ReadInt32(node,20)==2&&Marshal.ReadInt64(heap,112)==leases&&Marshal.ReadInt64(heap,56)==objects,"Notification released/changed recursive monitor or allocated");
            Marshal.WriteInt32(node,28,1);raw=new Context();Check(all(heap,value,ref raw)==20&&raw.Kind==20,"Unsupported nonempty wait metadata was ignored");Marshal.WriteInt32(node,28,0);
            var attempting=new System.Threading.ManualResetEventSlim(false);var acquired=new System.Threading.ManualResetEventSlim(false);var workerTask=System.Threading.Tasks.Task.Run(()=>{var c=new Context();Check(all(heap,value,ref c)==17&&c.Kind==17,"Nonowner thread notified monitor");c=new Context();attempting.Set();Check(enter(heap,value,ref c)==0,"Contending monitor enter failed");acquired.Set();Check(all(heap,value,ref c)==0&&leave(heap,value,ref c)==0,"Contending owner notification/release failed");});Check(attempting.Wait(5000),"Contender did not start");Check(System.Threading.SpinWait.SpinUntil(()=>Marshal.ReadInt32(node,24)>0,5000),"Contender not registered");raw=new Context();Check(all(heap,value,ref raw)==0&&!acquired.Wait(20),"notifyAll released ownership to entry contender");Check(leave(heap,value,ref raw)==0&&!acquired.Wait(20),"Partial recursive exit released ownership");Check(leave(heap,value,ref raw)==0&&workerTask.Wait(5000),"Final exit did not release entry contender");attempting.Dispose();acquired.Dispose();
            raw=new Context();Check(enter(heap,value,ref raw)==0,"Full-heap notification enter failed");while(alloc(heap,4096,0,267)!=IntPtr.Zero){}while(alloc(heap,0,0,267)!=IntPtr.Zero){}objects=Marshal.ReadInt64(heap,56);raw=new Context();Check(notify(heap,value,ref raw)==0&&all(heap,value,ref raw)==0&&Marshal.ReadInt64(heap,56)==objects,"Full-heap notification allocated/collected");Check(leave(heap,value,ref raw)==0,"Full-heap notification release failed");GC(m,heap);raw=new Context();Check(alloc(heap,32,0,267)!=IntPtr.Zero,"Notification heap did not recover after explicit GC");return results;
        }finally{if(m!=IntPtr.Zero)Check(Fn<Release>(m,"boom_release_trace_pool")()==0,"Notification Java frames remain");if(foreign!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(foreign);if(heap!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(heap);if(r!=IntPtr.Zero)FreeLibrary(r);if(m!=IntPtr.Zero)FreeLibrary(m);}
    }
}
