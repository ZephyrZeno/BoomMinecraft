// FFI and contention assertions only. The original System/Signal code is ASM.
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
public static class BoomSystemSignalMonitorProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr state,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ClassLoad(IntPtr ctx,IntPtr pool,int id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int ClassType(IntPtr ctx,IntPtr pool,IntPtr value);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Monitor(IntPtr heap,IntPtr value,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Entry(IntPtr ctx,IntPtr args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Release();
    static T Fn<T>(IntPtr dll,string name)where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(dll,name));}
    static void Need(bool value,string message){if(!value)throw new Exception(message);}
    static void Reset(IntPtr p){for(int i=0;i<32;i+=8)Marshal.WriteInt64(p,i,0);}
    public static long[] Run(string configuration){
        using var doc=JsonDocument.Parse(File.ReadAllText(configuration));var s=doc.RootElement;
        var runtime=NativeLibrary.Load(s.GetProperty("runtime").GetString());var image=NativeLibrary.Load(s.GetProperty("image").GetString());
        IntPtr heap=IntPtr.Zero;var ctx=Marshal.AllocHGlobal(32);bool success=false;
        try{
            Reset(ctx);heap=Fn<Create>(runtime,"boom_heap_create")(128UL*1024*1024);
            Need(heap!=IntPtr.Zero&&Fn<Bind>(image,"boom_java_string_literals_bind_heap")(heap)==1,"System monitor heap bind failed");
            var ensure=Fn<Ensure>(runtime,"boom_class_ensure32");
            foreach(var id in s.GetProperty("roots").EnumerateArray())Need(ensure(NativeLibrary.GetExport(image,"boom_class"+id.GetInt32()),ctx)==0&&Marshal.ReadInt32(ctx)==0,"Original System prerequisite failed");
            int type=s.GetProperty("monitor_class").GetInt32();var state=NativeLibrary.GetExport(image,"boom_class"+type);
            Need(Marshal.ReadInt32(state,8)==0,"Signal was initialized before the actual System path");
            var pool=NativeLibrary.GetExport(image,"boom_java_class_pool");var load=Fn<ClassLoad>(runtime,"boom_java_class_load");
            var mirror=load(ctx,pool,type);
            Need(mirror!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0&&load(ctx,pool,type)==mirror&&Fn<ClassType>(runtime,"boom_java_class_typeid")(ctx,pool,mirror)==type&&Marshal.ReadInt32(state,8)==0,"Canonical Signal Class identity or cold state differs");
            var enter=Fn<Monitor>(runtime,"boom_monitor_enter");var leave=Fn<Monitor>(runtime,"boom_monitor_exit");
            Need(enter(heap,mirror,ctx)==0&&Marshal.ReadInt32(ctx)==0,"Cannot acquire normal Signal Class monitor");
            Task<long[]> run=null;int waiters=0;bool observed=false;
            try{
                var node=Marshal.ReadIntPtr(heap,96);int scanned=0;
                while(node!=IntPtr.Zero&&Marshal.ReadIntPtr(node)!=mirror&&scanned++<4096)node=Marshal.ReadIntPtr(node,8);
                Need(node!=IntPtr.Zero&&Marshal.ReadIntPtr(node)==mirror&&Marshal.ReadInt32(node,20)==1,"Normal Signal Class monitor node missing");
                var entry=Fn<Entry>(image,s.GetProperty("entry").GetString());
                run=Task.Run(()=>{var c=Marshal.AllocHGlobal(32);var a=Marshal.AllocHGlobal(16);try{Reset(c);Marshal.WriteInt64(a,0);Marshal.WriteInt64(a,8,0);long value=entry(c,a);return new long[]{value,Marshal.ReadInt32(c),Marshal.ReadInt32(c,8),Marshal.ReadInt32(c,4),Marshal.ReadInt32(c,12)};}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});
                observed=SpinWait.SpinUntil(()=>Marshal.ReadInt32(node,24)>0||run.IsCompleted,TimeSpan.FromSeconds(15));waiters=Marshal.ReadInt32(node,24);
            }finally{Need(leave(heap,mirror,ctx)==0&&Marshal.ReadInt32(ctx)==0,"Cannot release normal Signal Class monitor");}
            Need(run!=null&&run.Wait(15000),"Original System did not return after monitor release");var result=run.GetAwaiter().GetResult();
            Need(observed&&waiters>0,"Original System did not contend on Signal Class: kind="+result[1]+" method="+result[2]+" pc="+result[3]);
            var diagnostic=NativeLibrary.GetExport(image,"boom_diagnostic_pool");
            Need(result[1]==0xb001&&result[4]==0&&Marshal.ReadInt32(diagnostic,8)==2&&Marshal.ReadInt32(diagnostic,32)==s.GetProperty("expected_stop_row").GetInt32(),"Original System did not reach the expected unprovided handle0 native");
            Need(Marshal.ReadInt32(state,8)==2,"Original Signal initializer did not complete");
            Need(Marshal.ReadInt64(heap,112)==0&&Marshal.ReadInt32(heap,104)==0,"System Signal synchronized envelope retained monitors");
            success=true;return new long[]{waiters,type,s.GetProperty("monitor_method").GetInt32(),result[2],result[3]};
        }finally{
            if(success)Need(Fn<Release>(image,"boom_release_trace_pool")()==0,"System monitor test retained source frames");
            if(heap!=IntPtr.Zero){int status=Fn<Destroy>(runtime,"boom_heap_destroy")(heap);if(success)Need(status==1,"System monitor heap cleanup failed");}
            Marshal.FreeHGlobal(ctx);if(success){NativeLibrary.Free(image);NativeLibrary.Free(runtime);}
        }
    }
}
