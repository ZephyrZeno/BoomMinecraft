using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

// Development caller only. Source initialization, registration and clock work
// execute ASM. Test fixture pools are distinct from the source VM pool.
public static class BoomNormalVmBootstrapProbe {
    [DllImport("kernel32.dll")] static extern void GetSystemTimePreciseAsFileTime(out ulong t);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr cls,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Entry(IntPtr ctx,IntPtr argv);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Kernel(IntPtr ctx,IntPtr argv,IntPtr pool,int op);
    static T Fn<T>(IntPtr m,string n) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(m,n));}
    static void Need(bool b,string s){if(!b)throw new Exception(s);}
    static void Reset(IntPtr c){for(int i=0;i<32;i+=8)Marshal.WriteInt64(c,i,0);Marshal.WriteInt32(c,4,37);Marshal.WriteInt32(c,8,73);}
    static IntPtr Memory(List<IntPtr> a,int n){IntPtr p=Marshal.AllocHGlobal(n);for(int i=0;i<n;i++)Marshal.WriteByte(p,i,0);a.Add(p);return p;}
    static long Expected(ulong time,long offset){decimal seconds=decimal.Floor(time/10000000m);decimal delta=seconds-11644473600m-offset;return delta<=-4294967296m||delta>=4294967296m?-1:(long)(delta*1000000000m+(time-seconds*10000000m)*100m);}
    static void Time(Entry f,IntPtr ctx,IntPtr args,long offset){
        Marshal.WriteInt64(args,offset);Reset(ctx);GetSystemTimePreciseAsFileTime(out ulong before);long value=f(ctx,args);GetSystemTimePreciseAsFileTime(out ulong after);
        long lo=Expected(before,offset),hi=Expected(after,offset);Need(Marshal.ReadInt32(ctx)==0&&value>=Math.Min(lo,hi)&&value<=Math.Max(lo,hi),"VM time outside Win32 bracket");
    }
    public static long[] Run(string runtime,string image,int classId,string initializeName,string adjustmentName,int initLevelField,int lockField,int directMemoryField){
        IntPtr lib=NativeLibrary.Load(runtime),dll=IntPtr.Zero,heap=IntPtr.Zero;var memory=new List<IntPtr>();var destroy=Fn<Destroy>(lib,"boom_heap_destroy");
        try {
            dll=NativeLibrary.Load(image);heap=Fn<Create>(lib,"boom_heap_create")(64UL*1024*1024);Need(heap!=IntPtr.Zero&&Fn<Bind>(dll,"boom_java_string_literals_bind_heap")(heap)==1,"VM source heap bind failed");
            IntPtr ctx=Memory(memory,32),args=Memory(memory,8),pool=NativeLibrary.GetExport(dll,"boom_java_vm_pool"),cls=NativeLibrary.GetExport(dll,"boom_class"+classId);
            IntPtr level=NativeLibrary.GetExport(dll,"boom_s"+classId+"_"+initLevelField),gate=NativeLibrary.GetExport(dll,"boom_s"+classId+"_"+lockField),direct=NativeLibrary.GetExport(dll,"boom_s"+classId+"_"+directMemoryField);
            Need(Marshal.ReadInt32(cls,8)==0&&Marshal.ReadInt32(pool,8)==0&&Marshal.ReadIntPtr(pool,16)==IntPtr.Zero&&Marshal.ReadIntPtr(gate)==IntPtr.Zero&&Marshal.ReadInt64(direct)==0,"VM source state was preinitialized");
            var kernel=Fn<Kernel>(lib,"boom_vm_native");var ensure=Fn<Ensure>(lib,"boom_class_ensure32");int errors=0;
            byte[] initial=new byte[32];Marshal.Copy(pool,initial,0,32);IntPtr fixture=Memory(memory,32);Marshal.Copy(initial,0,fixture,32);
            const int workers=8,iterations=1024;
            using(var barrier=new Barrier(workers))Parallel.For(0,workers,w=>{
                IntPtr c=Marshal.AllocHGlobal(32);try{barrier.SignalAndWait();for(int i=0;i<iterations;i++){Reset(c);Marshal.WriteInt64(c,16,0x12345678);Marshal.WriteInt64(c,24,0x23456789);Need(kernel(c,IntPtr.Zero,fixture,0)==0&&Marshal.ReadInt32(c)==0&&Marshal.ReadInt64(c,16)==0x12345678&&Marshal.ReadInt64(c,24)==0x23456789,"Concurrent ABI2 registration/prefix preservation failed");}}finally{Marshal.FreeHGlobal(c);}
            });
            IntPtr target=Marshal.ReadIntPtr(fixture,16);int pe=Marshal.ReadInt32(lib,0x3c),size=Marshal.ReadInt32(lib,pe+80);
            Need(Marshal.ReadInt32(fixture,8)==2&&target.ToInt64()>=lib.ToInt64()&&target.ToInt64()<lib.ToInt64()+size,"Registered entry is not inside the runtime DLL");
            Need(Marshal.ReadInt32(pool,8)==0&&Marshal.ReadInt32(cls,8)==0,"Fixture registration changed source preparation");
            using(var barrier=new Barrier(workers))Parallel.For(0,workers,w=>{
                IntPtr c=Marshal.AllocHGlobal(32);try{Reset(c);barrier.SignalAndWait();Need(ensure(cls,c)==0&&Marshal.ReadInt32(c)==0,"Original VM initializer failed");}finally{Marshal.FreeHGlobal(c);}
            });
            Need(Marshal.ReadInt32(cls,8)==2&&Marshal.ReadInt32(pool,8)==2&&Marshal.ReadIntPtr(pool,16)==target&&Marshal.ReadIntPtr(gate)!=IntPtr.Zero&&Marshal.ReadInt64(direct)==67108864L&&Marshal.ReadInt32(level)==0,"Original VM Java state/registration differs");
            var initialize=Fn<Entry>(dll,initializeName);var adjustment=Fn<Entry>(dll,adjustmentName);
            foreach(long offset in new long[]{0,-1,1,long.MinValue,long.MaxValue,DateTimeOffset.UtcNow.ToUnixTimeSeconds()})Time(adjustment,ctx,args,offset);
            Parallel.For(0,workers,w=>{
                IntPtr c=Marshal.AllocHGlobal(32),a=Marshal.AllocHGlobal(8);try{for(int i=0;i<iterations;i++)Time(adjustment,c,a,(i&1)==0?0:DateTimeOffset.UtcNow.ToUnixTimeSeconds());}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}
            });
            Reset(ctx);Need(initialize(ctx,args)==0&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt32(level)==0,"Repeated registration changed Java boot level");
            byte[] ready=new byte[32];Marshal.Copy(pool,ready,0,32);IntPtr copy=Memory(memory,32);
            foreach(int offset in new[]{0,4,8,12,24}){
                Marshal.Copy(ready,0,copy,32);Marshal.WriteInt32(copy,offset,1234567);Reset(ctx);Need(kernel(ctx,args,copy,0)==0&&Marshal.ReadInt32(ctx)==7,"Invalid VM metadata accepted: "+offset);errors++;
            }
            Marshal.Copy(initial,0,copy,32);Marshal.WriteIntPtr(copy,16,fixture);Reset(ctx);Need(kernel(ctx,args,copy,0)==0&&Marshal.ReadInt32(ctx)==7&&Marshal.ReadInt32(copy,8)==0,"Foreign registration target accepted");errors++;
            Marshal.Copy(initial,0,copy,32);Marshal.WriteInt32(copy,8,2);Reset(ctx);Need(kernel(ctx,args,copy,0)==0&&Marshal.ReadInt32(ctx)==7,"Ready pool without target repaired silently");errors++;
            Marshal.Copy(initial,0,copy,32);Reset(ctx);Need(kernel(ctx,args,copy,1)==0&&Marshal.ReadInt32(ctx)==7,"Unregistered time query accepted");errors++;
            Reset(ctx);Need(kernel(ctx,IntPtr.Zero,pool,1)==0&&Marshal.ReadInt32(ctx)==7,"Null time arguments accepted");errors++;
            Reset(ctx);Need(kernel(ctx,args,pool,99)==0&&Marshal.ReadInt32(ctx)==7,"Unknown operation accepted");errors++;
            Marshal.Copy(initial,0,copy,32);Reset(ctx);Marshal.WriteInt32(ctx,99);Need(kernel(ctx,args,copy,0)==0&&Marshal.ReadInt32(ctx)==99&&Marshal.ReadInt32(ctx,4)==37&&Marshal.ReadIntPtr(copy,16)==IntPtr.Zero,"Pending VM error overwritten or registration executed");errors++;
            Need(kernel(IntPtr.Zero,args,copy,0)==0&&Marshal.ReadIntPtr(copy,16)==IntPtr.Zero,"Null context installed a target");errors++;
            // ABI1 remains available to the older development compiler.
            Marshal.Copy(ready,0,copy,32);Marshal.WriteInt32(copy,4,1);Marshal.WriteInt32(copy,8,0);Reset(ctx);
            Need(kernel(ctx,args,copy,0)==0&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt32(copy,8)==2,"Legacy ABI1 registration regressed");
            Marshal.WriteInt64(args,long.MaxValue);Reset(ctx);Need(kernel(ctx,args,copy,1)==-1&&Marshal.ReadInt32(ctx)==0,"Legacy ABI1 clock dispatch regressed");
            Need(Marshal.ReadInt32(NativeLibrary.GetExport(dll,"boom_diagnostic_pool"),8)==0,"VM probe reached an unimplemented source dependency");
            return new long[]{workers,workers*iterations,workers*iterations,6,errors,Marshal.ReadInt64(heap,56)};
        }finally{if(heap!=IntPtr.Zero)Need(destroy(heap)==1,"VM heap cleanup failed");for(int i=memory.Count-1;i>=0;i--)Marshal.FreeHGlobal(memory[i]);if(dll!=IntPtr.Zero)NativeLibrary.Free(dll);NativeLibrary.Free(lib);}
    }
}
