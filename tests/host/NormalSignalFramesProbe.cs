// FFI and metadata/callback fixtures only. Transport, leases and queries are MASM.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
public static class BoomNormalSignalFramesProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr control,IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Query(IntPtr ctx,IntPtr args,IntPtr pool,int operation);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(IntPtr config);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Close(IntPtr control);
    static T Fn<T>(IntPtr dll,string name)where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(dll,name));}
    static void Need(bool condition,string message){if(!condition)throw new Exception(message);}
    static IntPtr Zero(List<IntPtr> owned,int bytes){var p=Marshal.AllocHGlobal(bytes);Marshal.Copy(new byte[bytes],0,p,bytes);owned.Add(p);return p;}
    static void Reset(IntPtr p){for(int i=0;i<32;i+=8)Marshal.WriteInt64(p,i,0);}
    public static long[] Run(string configuration,string adapter){
        using var doc=JsonDocument.Parse(File.ReadAllText(configuration));var s=doc.RootElement;
        var runtime=NativeLibrary.Load(s.GetProperty("runtime").GetString());var image=NativeLibrary.Load(s.GetProperty("image").GetString());var callbacks=NativeLibrary.Load(adapter);
        var owned=new List<IntPtr>();IntPtr control=IntPtr.Zero;bool bound=false;
        var bind=Fn<Bind>(runtime,"boom_signal_native_bind");var query=Fn<Query>(runtime,"boom_signal_native_query");var close=Fn<Close>(runtime,"boom_signal_control_close");
        var pool=Zero(owned,64);var trace=Zero(owned,48);var legacy=Zero(owned,48);var row=Zero(owned,32);var ctx=Zero(owned,32);var args=Zero(owned,16);var user=Zero(owned,256);var config=Zero(owned,48);
        try{
            var actual=NativeLibrary.GetExport(image,"boom_trace_pool");var bytes=new byte[48];Marshal.Copy(actual,bytes,0,48);Marshal.Copy(bytes,0,trace,48);
            int sourceMethods=Marshal.ReadInt32(trace,16);Need(Marshal.ReadInt32(trace)==0x5452504c&&Marshal.ReadInt32(trace,4)==3&&sourceMethods>262144&&sourceMethods<=1048576,"Normal source TracePool3 identity/count differs");
            Marshal.WriteInt32(pool,0x504e4753);Marshal.WriteInt32(pool,4,1);Marshal.WriteIntPtr(pool,32,trace);
            Need(bind(IntPtr.Zero,pool)==0,"Normal source frame pool rejected by signal binding");
            Marshal.WriteInt32(legacy,0x5452504c);Marshal.WriteInt32(legacy,4,2);Marshal.WriteInt32(legacy,12,-1);Marshal.WriteInt32(legacy,16,1);Marshal.WriteIntPtr(legacy,24,row);
            Marshal.WriteIntPtr(pool,32,legacy);Need(bind(IntPtr.Zero,pool)==0,"Legacy TracePool2 signal binding changed");Marshal.WriteIntPtr(pool,32,trace);
            int errors=0;
            Action<int,int> bad32=(offset,value)=>{int saved=Marshal.ReadInt32(trace,offset);Marshal.WriteInt32(trace,offset,value);Need(bind(IntPtr.Zero,pool)==87,"Invalid signal frame metadata accepted: "+offset+"="+value);Marshal.WriteInt32(trace,offset,saved);errors++;};
            bad32(0,0);bad32(4,1);bad32(4,4);bad32(8,5);bad32(16,0);bad32(16,1048577);bad32(20,1);bad32(44,1);
            var rows=Marshal.ReadIntPtr(trace,24);Marshal.WriteIntPtr(trace,24,IntPtr.Zero);Need(bind(IntPtr.Zero,pool)==87,"Missing signal trace rows accepted");Marshal.WriteIntPtr(trace,24,rows);errors++;
            Marshal.WriteIntPtr(pool,32,legacy);Marshal.WriteInt32(legacy,16,262145);Need(bind(IntPtr.Zero,pool)==87,"Legacy signal frame count overflow accepted");Marshal.WriteInt32(legacy,16,1);Marshal.WriteIntPtr(pool,32,trace);errors++;
            foreach(int offset in new[]{40,48,56}){Marshal.WriteInt64(pool,offset,1);Need(bind(IntPtr.Zero,pool)==87,"Reserved signal binding field accepted");Marshal.WriteInt64(pool,offset,0);errors++;}
            Marshal.WriteInt64(pool,16,1);Need(bind(IntPtr.Zero,pool)==170,"Active native signal lease ignored");Marshal.WriteInt64(pool,16,0);errors++;
            Marshal.WriteInt64(trace,32,1);Need(bind(IntPtr.Zero,pool)==170,"Active source frame lease ignored");Marshal.WriteInt64(trace,32,0);errors++;
            Marshal.WriteInt32(trace,40,1);Need(bind(IntPtr.Zero,pool)==170,"Closing source frames ignored");Marshal.WriteInt32(trace,40,0);errors++;
            int state=Marshal.ReadInt32(trace,8);Marshal.WriteInt32(trace,8,4);Need(bind(IntPtr.Zero,pool)==87,"Released source frame pool accepted");Marshal.WriteInt32(trace,8,state);errors++;
            Reset(ctx);Marshal.WriteInt32(ctx,9);Marshal.WriteInt32(ctx,4,123);Marshal.WriteInt32(ctx,8,456);Marshal.WriteInt32(ctx,12,7);Marshal.WriteInt64(ctx,16,0x12345678);
            Need(query(ctx,IntPtr.Zero,IntPtr.Zero,0)==0&&Marshal.ReadInt32(ctx)==9&&Marshal.ReadInt32(ctx,4)==123&&Marshal.ReadInt32(ctx,8)==456&&Marshal.ReadInt32(ctx,12)==7&&Marshal.ReadInt64(ctx,16)==0x12345678,"Pending signal Context32 changed");errors++;
            Marshal.WriteInt32(config,0x53474346);Marshal.WriteInt32(config,4,1);Marshal.WriteIntPtr(config,8,NativeLibrary.GetExport(callbacks,"boom_signal_test_dispatch"));Marshal.WriteIntPtr(config,16,NativeLibrary.GetExport(callbacks,"boom_signal_test_break"));Marshal.WriteIntPtr(config,24,user);
            control=Fn<Create>(runtime,"boom_signal_control_create")(config);Need(control!=IntPtr.Zero,"Signal transport fixture creation failed");
            Need(bind(control,pool)==0&&bind(control,pool)==0,"Signal transport did not bind to normal source frames");bound=true;
            Need(bind(IntPtr.Zero,pool)==170,"Live signal transport was unbound");errors++;
            Func<int,long,long> register=(number,handler)=>{Reset(ctx);Marshal.WriteInt64(args,number);Marshal.WriteInt64(args,8,handler);long value=query(ctx,args,pool,0);Need(Marshal.ReadInt32(ctx)==0,"Signal registration Context differs");return value;};
            register(15,0);Need(register(15,1)==0&&register(15,2)==1,"Native signal registration result differs");
            Reset(ctx);Marshal.WriteInt64(args,15);Need(query(ctx,args,pool,1)==0&&Marshal.ReadInt32(ctx)==0,"Signal dispatch enqueue failed");
            Need(SpinWait.SpinUntil(()=>Marshal.ReadInt64(user,15*8)==1,TimeSpan.FromSeconds(10)),"Assembly signal callback was not delivered");
            Need(Marshal.ReadInt64(user,192)==0,"Signal callback floating-point state differs");
            Need(register(-1,1)==-1,"Native invalid-number rejection changed");Need(register(8,1)==-1&&register(21,1)==-1,"VM-owned signal rejection changed");
            register(15,1);const int workers=8,iterations=2048;
            Parallel.For(0,workers,w=>{var c=Marshal.AllocHGlobal(32);var a=Marshal.AllocHGlobal(16);try{for(int i=0;i<iterations;i++){Reset(c);Marshal.WriteInt64(a,15);Marshal.WriteInt64(a,8,1);Need(query(c,a,pool,0)==1&&Marshal.ReadInt32(c)==0,"Concurrent normal-frame signal query failed");}}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});
            Need(Marshal.ReadInt64(pool,16)==0&&Marshal.ReadInt64(trace,32)==0,"Native signal/source frame leases leaked");
            Need(close(control)==0,"Signal transport close/join failed");control=IntPtr.Zero;Need(bind(IntPtr.Zero,pool)==0,"Closed transport did not unbind");bound=false;
            return new long[]{sourceMethods,2,errors,1,workers,workers*iterations};
        }finally{
            if(control!=IntPtr.Zero)Need(close(control)==0,"Signal fixture cleanup close failed");
            if(bound)Need(bind(IntPtr.Zero,pool)==0,"Signal fixture cleanup unbind failed");
            foreach(var p in owned)Marshal.FreeHGlobal(p);NativeLibrary.Free(callbacks);NativeLibrary.Free(image);NativeLibrary.Free(runtime);
        }
    }
}
