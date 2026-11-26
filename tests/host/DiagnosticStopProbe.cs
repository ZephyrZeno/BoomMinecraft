using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

// Explicit development ABI fixture, not an original Java class/runtime proof.
public static class BoomDiagnosticStopProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Stop(IntPtr ctx,IntPtr row,IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr cls,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Unary(IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Match(IntPtr ctx,int pc,IntPtr table);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void Failed(IntPtr ctx,IntPtr cls);
    static T Fn<T>(IntPtr lib,string name) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(lib,name));}
    static void Need(bool ok,string s){if(!ok)throw new Exception(s);}
    static IntPtr Memory(List<IntPtr> m,int n){IntPtr p=Marshal.AllocHGlobal(n);for(int i=0;i<n;i++)Marshal.WriteByte(p,i,0);m.Add(p);return p;}
    static void Reset(IntPtr c){for(int i=0;i<32;i+=8)Marshal.WriteInt64(c,i,0);Marshal.WriteInt32(c,4,37);Marshal.WriteInt32(c,8,73);}
    public static long[] Run(string runtime,string fixture){
        IntPtr lib=NativeLibrary.Load(runtime),dll=NativeLibrary.Load(fixture);var memory=new List<IntPtr>();
        try {
            var stop=Fn<Stop>(dll,"boom_diagnostic_stop");var ensure=Fn<Ensure>(lib,"boom_class_ensure32");
            IntPtr original=NativeLibrary.GetExport(dll,"boom_diagnostic_pool"),rows=NativeLibrary.GetExport(dll,"boom_diagnostic_rows");
            IntPtr pool=Memory(memory,96),ctx=Memory(memory,32);byte[] metadata=new byte[96];Marshal.Copy(original,metadata,0,96);int checks=0;
            Marshal.Copy(metadata,0,pool,96);Reset(ctx);Need(stop(ctx,rows,pool)==0&&Marshal.ReadInt32(ctx)==0xB001&&Marshal.ReadInt32(pool,8)==2&&Marshal.ReadInt32(pool,32)==1&&Marshal.ReadInt32(pool,44)==37&&Marshal.ReadInt32(pool,48)==73,"Failure record ABI differs");checks++;
            Need(Fn<Unary>(lib,"boom_exception_materialize")(ctx)!=0&&Marshal.ReadInt32(ctx)==0xB001,"Diagnostic stop became a guest exception");checks++;
            Need(Fn<Match>(lib,"boom_exception_match32")(ctx,0,IntPtr.Zero)==0&&Marshal.ReadInt32(ctx)==0xB001,"Diagnostic stop was caught by Java handler");checks++;
            Marshal.Copy(metadata,0,pool,96);Reset(ctx);Marshal.WriteInt32(ctx,99);Need(stop(ctx,rows,pool)==0&&Marshal.ReadInt32(ctx)==99&&Marshal.ReadInt32(pool,8)==0,"Pending error was overwritten");checks++;
            Need(stop(IntPtr.Zero,rows,pool)==0&&Marshal.ReadInt32(pool,8)==0,"Null context published a record");checks++;
            foreach(int offset in new[]{0,4,8,12,24,28}){
                Marshal.Copy(metadata,0,pool,96);Marshal.WriteInt32(pool,offset,offset==12?0:12345);Reset(ctx);
                Need(stop(ctx,rows,pool)==0&&Marshal.ReadInt32(ctx)==7,"Invalid stop pool accepted: "+offset);checks++;
            }
            IntPtr foreign=Memory(memory,48);Marshal.WriteInt32(foreign,1);Marshal.Copy(metadata,0,pool,96);Reset(ctx);
            Need(stop(ctx,foreign,pool)==0&&Marshal.ReadInt32(ctx)==7,"Foreign diagnostic row accepted");checks++;
            Reset(ctx);Need(stop(ctx,IntPtr.Zero,pool)==0&&Marshal.ReadInt32(ctx)==7,"Null row accepted");checks++;
            Marshal.Copy(metadata,0,pool,96);const int workers=8,iterations=1024;
            using(var barrier=new Barrier(workers))Parallel.For(0,workers,w=>{
                IntPtr c=Marshal.AllocHGlobal(32);try{barrier.SignalAndWait();for(int i=0;i<iterations;i++){Reset(c);Need(stop(c,rows,pool)==0&&Marshal.ReadInt32(c)==0xB001,"Concurrent diagnostic call lost stop");}}finally{Marshal.FreeHGlobal(c);}
            });
            Need(Marshal.ReadInt32(pool,8)==2&&Marshal.ReadInt32(pool,32)==1,"Concurrent first-fault record not published");
            IntPtr descriptor=Memory(memory,64),cause=Memory(memory,8);
            Marshal.WriteInt32(descriptor,0,0x434c4153);Marshal.WriteInt32(descriptor,4,2);Marshal.WriteIntPtr(descriptor,16,NativeLibrary.GetExport(dll,"boom_m987654"));Marshal.WriteInt32(descriptor,24,1);Marshal.WriteIntPtr(descriptor,56,cause);
            Reset(ctx);Need(ensure(descriptor,ctx)!=0&&Marshal.ReadInt32(ctx)==0xB001&&Marshal.ReadInt32(descriptor,8)==3,"Failed fixture initializer did not propagate stop");checks++;
            Reset(ctx);Need(ensure(descriptor,ctx)!=0&&Marshal.ReadInt32(ctx)==9&&Marshal.ReadInt32(ctx,4)==37&&Marshal.ReadInt32(ctx,8)==73,"Repeated failed class with unbound exception pool differs");checks++;
            var failed=Fn<Failed>(lib,"boom_exception_class_failed");failed(IntPtr.Zero,descriptor);checks++;
            IntPtr vm=Memory(memory,32);
            foreach(int mode in new[]{0,1,2}){
                for(int i=0;i<32;i+=8)Marshal.WriteInt64(vm,i,0);
                if(mode>0)Marshal.WriteInt32(vm,0,0x4558564d);Marshal.WriteInt32(vm,4,mode==1?99:1);
                Reset(ctx);Marshal.WriteIntPtr(ctx,24,vm);failed(ctx,descriptor);
                Need(Marshal.ReadInt32(ctx)==9,"Incompatible/unprepared VM exception pool accepted");checks++;
            }
            return new long[]{checks,workers*iterations,workers};
        }finally{for(int i=memory.Count-1;i>=0;i--)Marshal.FreeHGlobal(memory[i]);NativeLibrary.Free(dll);NativeLibrary.Free(lib);}
    }
}
