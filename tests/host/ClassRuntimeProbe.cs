using System;
using System.Runtime.InteropServices;
using System.Threading;
using System.Diagnostics;
public static class BoomClassRuntimeProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {public uint Kind,PC,Method,Reserved;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr descriptor,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void Configure(IntPtr descriptor,IntPtr gate,IntPtr count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong FpCall(IntPtr entry,ref Context context,[In] ulong[] args,uint csr);
    static IntPtr NewDescriptor(IntPtr initializer) {
        IntPtr value=Marshal.AllocHGlobal(64);for(int i=0;i<64;i+=8)Marshal.WriteInt64(value,i,0);
        Marshal.WriteInt32(value,0,0x434c4153);Marshal.WriteInt32(value,4,1);Marshal.WriteIntPtr(value,16,initializer);Marshal.WriteInt32(value,24,42);return value;
    }
    public static void Run(string dll,string fpProbe) {
        IntPtr module=LoadLibraryExW(dll,IntPtr.Zero,0x1100);if(module==IntPtr.Zero)throw new Exception("Class probe load failed");
        IntPtr descriptor=IntPtr.Zero,gate=IntPtr.Zero,count=IntPtr.Zero,fpLibrary=IntPtr.Zero;Thread[] threads=new Thread[12];
        var start=new ManualResetEvent(false);var ready=new CountdownEvent(threads.Length);
        try {
            var ensure=Marshal.GetDelegateForFunctionPointer<Ensure>(GetProcAddress(module,"boom_class_ensure"));
            var configure=Marshal.GetDelegateForFunctionPointer<Configure>(GetProcAddress(module,"boom_probe_configure_class"));
            descriptor=NewDescriptor(GetProcAddress(module,"boom_probe_class_initializer"));gate=Marshal.AllocHGlobal(4);count=Marshal.AllocHGlobal(8);Marshal.WriteInt32(gate,0);Marshal.WriteInt64(count,0);configure(descriptor,gate,count);
            var statuses=new int[threads.Length];var contexts=new Context[threads.Length];var failures=new Exception[threads.Length];
            for(int i=0;i<threads.Length;i++){int index=i;threads[i]=new Thread(()=>{ready.Signal();start.WaitOne();try{statuses[index]=ensure(descriptor,ref contexts[index]);}catch(Exception error){failures[index]=error;}});threads[i].Start();}
            if(!ready.Wait(5000))throw new Exception("Class race threads did not start");start.Set();
            var watch=Stopwatch.StartNew();while(Marshal.ReadInt64(count)==0&&watch.ElapsedMilliseconds<5000)Thread.Yield();
            while(Marshal.ReadInt32(descriptor,48)!=threads.Length-1&&watch.ElapsedMilliseconds<5000)Thread.Yield();
            if(Marshal.ReadInt64(count)!=1||Marshal.ReadInt32(descriptor,8)!=1||Marshal.ReadInt32(descriptor,12)==0||Marshal.ReadInt32(descriptor,48)!=threads.Length-1)throw new Exception("Class initializer ownership/waiters incorrect");
            Marshal.WriteInt32(gate,1);
            for(int i=0;i<threads.Length;i++){if(!threads[i].Join(5000))throw new Exception("Initialization waiters did not wake");if(failures[i]!=null)throw failures[i];if(statuses[i]!=0||contexts[i].Kind!=0)throw new Exception("Waiter saw invalid class status");}
            if(Marshal.ReadInt32(descriptor,8)!=2||Marshal.ReadInt32(descriptor,12)!=0||Marshal.ReadInt64(count)!=1||Marshal.ReadInt32(descriptor,48)!=0)throw new Exception("Class initialization publication failed");
            for(int i=0;i<100;i++){var context=new Context();if(ensure(descriptor,ref context)!=0||context.Kind!=0)throw new Exception("Initialized fast path failed");}
            if(Marshal.ReadInt64(count)!=1)throw new Exception("Initialized class replayed callback");
            Marshal.FreeHGlobal(descriptor);descriptor=IntPtr.Zero;
            foreach(string symbol in new[]{"boom_probe_class_failure","boom_probe_class_error"}) {
                descriptor=NewDescriptor(GetProcAddress(module,symbol));var context=new Context();uint first=symbol.EndsWith("failure")?8u:3u,cause=symbol.EndsWith("failure")?1u:3u;
                if(ensure(descriptor,ref context)!=1||context.Kind!=first||unchecked((uint)Marshal.ReadInt32(descriptor,32))!=cause||Marshal.ReadInt32(descriptor,8)!=3)throw new Exception("Class failure publication incorrect");
                context=new Context();if(ensure(descriptor,ref context)!=1||context.Kind!=9)throw new Exception("Failed class was retried");
                Marshal.FreeHGlobal(descriptor);descriptor=IntPtr.Zero;
            }
            descriptor=NewDescriptor(IntPtr.Zero);var empty=new Context();if(ensure(descriptor,ref empty)!=0||Marshal.ReadInt32(descriptor,8)!=2)throw new Exception("Empty initializer failed");
            Marshal.WriteInt32(descriptor,4,2);empty=new Context();if(ensure(descriptor,ref empty)!=1||empty.Kind!=7)throw new Exception("Wrong class ABI accepted");
            Marshal.FreeHGlobal(descriptor);descriptor=NewDescriptor(GetProcAddress(module,"boom_probe_class_floating"));Marshal.WriteInt64(count,0);configure(descriptor,gate,count);
            fpLibrary=LoadLibraryExW(fpProbe,IntPtr.Zero,0x1100);if(fpLibrary==IntPtr.Zero)throw new Exception("Class FP probe load failed");
            var fp=Marshal.GetDelegateForFunctionPointer<FpCall>(GetProcAddress(fpLibrary,"boom_probe_numeric"));empty=new Context();
            fp(GetProcAddress(module,"boom_probe_ensure_entry"),ref empty,new ulong[0],0x5f80);
            if(empty.Kind!=0||empty.Reserved!=0x5f80||Marshal.ReadInt64(count)!=0x4b800000)throw new Exception("Class initializer inherited caller floating-point mode");
        }finally {
            start.Set();if(gate!=IntPtr.Zero)Marshal.WriteInt32(gate,1);bool stopped=true;
            foreach(var thread in threads)if(thread!=null&&thread.IsAlive&&!thread.Join(1000))stopped=false;
            // Parent timeout kills this test process if native waiting is broken.
            if(stopped){if(descriptor!=IntPtr.Zero)Marshal.FreeHGlobal(descriptor);if(gate!=IntPtr.Zero)Marshal.FreeHGlobal(gate);if(count!=IntPtr.Zero)Marshal.FreeHGlobal(count);if(fpLibrary!=IntPtr.Zero)FreeLibrary(fpLibrary);FreeLibrary(module);start.Dispose();ready.Dispose();}
        }
    }
}
