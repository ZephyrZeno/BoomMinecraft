// FFI and assertions only. Original class initializers, FileDescriptor(int)
// constructors and all six native bindings execute the assembly source image.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
public static class BoomFileBootstrapSourceProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr state,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Entry(IntPtr ctx,IntPtr args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ClassLoad(IntPtr ctx,IntPtr pool,int type);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int ClassType(IntPtr ctx,IntPtr pool,IntPtr value);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Monitor(IntPtr heap,IntPtr value,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Release();
    [DllImport("kernel32.dll")] static extern IntPtr GetStdHandle(int handle);
    static T Fn<T>(IntPtr dll,string name)where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(dll,name));}
    static void Need(bool value,string message){if(!value)throw new Exception(message);}
    static void Reset(IntPtr p){for(int i=0;i<32;i+=8)Marshal.WriteInt64(p,i,0);}
    public static long[] Run(string configuration){return Run(configuration,2,false);}
    public static long[] Run(string configuration,int first,bool verifyClassMonitor){
        Need(first>=0&&first<3&&(!verifyClassMonitor||first==1),"Invalid cold file initialization order");
        using var doc=JsonDocument.Parse(File.ReadAllText(configuration));var s=doc.RootElement;
        IntPtr lib=NativeLibrary.Load(s.GetProperty("runtime").GetString()),image=NativeLibrary.Load(s.GetProperty("image").GetString()),heap=IntPtr.Zero;
        var ctx=Marshal.AllocHGlobal(32);var args=Marshal.AllocHGlobal(16);bool success=false;
        try{
            Reset(ctx);Marshal.WriteInt64(args,0);Marshal.WriteInt64(args,8,0);heap=Fn<Create>(lib,"boom_heap_create")(128UL*1024*1024);
            Need(heap!=IntPtr.Zero&&Fn<Bind>(image,"boom_java_string_literals_bind_heap")(heap)==1,"File source heap bind failed");
            var ensure=Fn<Ensure>(lib,"boom_class_ensure32");
            foreach(var id in s.GetProperty("roots").EnumerateArray())Need(ensure(NativeLibrary.GetExport(image,"boom_class"+id.GetInt32()),ctx)==0&&Marshal.ReadInt32(ctx)==0,"File source VM prerequisite failed");
            int cold=0;foreach(var id in s.GetProperty("owner_classes").EnumerateArray()){Need(Marshal.ReadInt32(NativeLibrary.GetExport(image,"boom_class"+id.GetInt32()),8)==0,"File initializer was already warmed");cold++;}
            var entries=new Entry[6];for(int i=0;i<6;i++)entries[i]=Fn<Entry>(image,s.GetProperty("native_symbols").GetProperty(i.ToString()).GetString());
            int monitorWaiters=0;
            if(verifyClassMonitor){
                int reflection=s.GetProperty("normal_Class_monitor_source").GetProperty("class_id").GetInt32();
                Need(ensure(NativeLibrary.GetExport(image,"boom_class"+reflection),ctx)==0&&Marshal.ReadInt32(ctx)==0,"Original Reflection prerequisite failed");
                foreach(var id in s.GetProperty("owner_classes").EnumerateArray())Need(Marshal.ReadInt32(NativeLibrary.GetExport(image,"boom_class"+id.GetInt32()),8)==0,"Reflection prerequisite warmed a file owner");
                var classPool=NativeLibrary.GetExport(image,"boom_java_class_pool");var load=Fn<ClassLoad>(lib,"boom_java_class_load");
                var mirror=load(ctx,classPool,reflection);
                Need(mirror!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0&&load(ctx,classPool,reflection)==mirror&&Fn<ClassType>(lib,"boom_java_class_typeid")(ctx,classPool,mirror)==reflection,"Reflection Class identity differs");
                var enter=Fn<Monitor>(lib,"boom_monitor_enter");var leave=Fn<Monitor>(lib,"boom_monitor_exit");
                Need(enter(heap,mirror,ctx)==0&&Marshal.ReadInt32(ctx)==0,"Cannot acquire normal Reflection Class monitor");
                Task<long[]> initialize=null;bool reached=false;
                try{
                    var node=Marshal.ReadIntPtr(heap,96);int scanned=0;
                    while(node!=IntPtr.Zero&&Marshal.ReadIntPtr(node)!=mirror&&scanned++<4096)node=Marshal.ReadIntPtr(node,8);
                    Need(node!=IntPtr.Zero&&Marshal.ReadIntPtr(node)==mirror&&Marshal.ReadInt32(node,20)==1,"Canonical Class monitor node missing");
                    initialize=Task.Run(()=>{
                        var c=Marshal.AllocHGlobal(32);var a=Marshal.AllocHGlobal(16);
                        try{Reset(c);Marshal.WriteInt64(a,0);Marshal.WriteInt64(a,8,0);long value=entries[1](c,a);return new long[]{value,Marshal.ReadInt32(c),Marshal.ReadInt32(c,8),Marshal.ReadInt32(c,4)};}
                        finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}
                    });
                    reached=SpinWait.SpinUntil(()=>Marshal.ReadInt32(node,24)>0||initialize.IsCompleted,TimeSpan.FromSeconds(5));
                    monitorWaiters=Marshal.ReadInt32(node,24);
                }finally{Need(leave(heap,mirror,ctx)==0&&Marshal.ReadInt32(ctx)==0,"Cannot release normal Reflection Class monitor");}
                Need(initialize!=null&&initialize.Wait(15000),"Cold file initializer did not finish after Class monitor release");
                var completed=initialize.GetAwaiter().GetResult();
                Need(reached&&monitorWaiters>0,"Original file initializer did not contend on canonical Reflection Class monitor: kind="+completed[1]+" method="+completed[2]+" pc="+completed[3]);
                Need(completed[0]==0&&completed[1]==0,"Cold output initializer failed after monitor release: kind="+completed[1]+" method="+completed[2]+" pc="+completed[3]);
            }
            int[] order=first==2?new[]{2,0,1}:first==1?new[]{1,0,2}:new[]{0,1,2};
            foreach(int i in order){if(verifyClassMonitor&&i==1)continue;Need(entries[i](ctx,args)==0&&Marshal.ReadInt32(ctx)==0,"Original file native initializer failed: "+i+" kind="+Marshal.ReadInt32(ctx)+" method="+Marshal.ReadInt32(ctx,8)+" pc="+Marshal.ReadInt32(ctx,4));}
            Need(entries[5](ctx,args)==(BitConverter.IsLittleEndian?0:1)&&Marshal.ReadInt32(ctx)==0,"Original UTF16 native byte-order query differs");
            foreach(var id in s.GetProperty("owner_classes").EnumerateArray())Need(Marshal.ReadInt32(NativeLibrary.GetExport(image,"boom_class"+id.GetInt32()),8)==2,"Original file class did not finish initialization");
            var shifts=s.GetProperty("utf16_shifts");Need(Marshal.ReadInt32(NativeLibrary.GetExport(image,shifts.GetProperty("HI_BYTE_SHIFT").GetString()))==(BitConverter.IsLittleEndian?0:8)&&Marshal.ReadInt32(NativeLibrary.GetExport(image,shifts.GetProperty("LO_BYTE_SHIFT").GetString()))==(BitConverter.IsLittleEndian?8:0),"Original UTF16 initializer did not publish native shifts");
            var meta=s.GetProperty("metadata");var fields=new Dictionary<string,int>();foreach(var f in meta.GetProperty("descriptor").GetProperty("fields").EnumerateArray())fields[f.GetProperty("name").GetString()]=f.GetProperty("offset").GetInt32();
            var pool=NativeLibrary.GetExport(image,"boom_provider_file_bootstrap_pool");var fdPool=Marshal.ReadIntPtr(pool,24);var layout=Marshal.ReadIntPtr(Marshal.ReadIntPtr(fdPool,8),8);
            int number=0;foreach(string name in new[]{"in","out","err"}){
                var cell=NativeLibrary.GetExport(image,s.GetProperty("standard_roots").GetProperty(name).GetString());var obj=Marshal.ReadIntPtr(cell);
                Need(obj!=IntPtr.Zero&&Marshal.ReadIntPtr(obj,-8)==layout&&Marshal.ReadInt32(obj,fields["fd"])==number&&Marshal.ReadInt64(obj,fields["handle"])==GetStdHandle(-10-number).ToInt64()&&Marshal.ReadByte(obj,fields["append"])==0,"Original Java standard descriptor constructor fields differ: "+name);number++;
            }
            int cases=0;foreach(int fd in new[]{int.MinValue,-2,-1,0,1,2,3,int.MaxValue}){
                Marshal.WriteInt64(args,fd);long expected=fd>=0&&fd<=2?GetStdHandle(-10-fd).ToInt64():-1;
                Need(entries[3](ctx,args)==expected&&entries[4](ctx,args)==0&&Marshal.ReadInt32(ctx)==0,"Original descriptor native query differs");cases++;
            }
            const int workers=8,iterations=1024;
            Parallel.For(0,workers,w=>{var c=Marshal.AllocHGlobal(32);var a=Marshal.AllocHGlobal(16);try{for(int i=0;i<iterations;i++){Reset(c);int fd=i%3;Marshal.WriteInt64(a,fd);Need(entries[3](c,a)==GetStdHandle(-10-fd).ToInt64()&&entries[4](c,a)==0&&entries[fd](c,a)==0&&Marshal.ReadInt32(c)==0,"Concurrent original file native failed");}}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});
            Need(Marshal.ReadInt32(NativeLibrary.GetExport(image,"boom_diagnostic_pool"),8)==0,"Original file bootstrap reached an unavailable dependency");
            Need(Marshal.ReadInt64(heap,112)==0&&Marshal.ReadInt32(heap,104)==0,"Original file source retained monitors");
            success=true;return new long[]{cold,number,cases,workers,workers*iterations*3,verifyClassMonitor?1:0,monitorWaiters};
        }finally{
            if(success)Need(Fn<Release>(image,"boom_release_trace_pool")()==0,"Original file source retained frames");
            if(heap!=IntPtr.Zero){int freed=Fn<Destroy>(lib,"boom_heap_destroy")(heap);if(success)Need(freed==1,"Original file source heap cleanup failed");}
            Marshal.FreeHGlobal(args);Marshal.FreeHGlobal(ctx);if(success){NativeLibrary.Free(image);NativeLibrary.Free(lib);}
        }
    }
}
