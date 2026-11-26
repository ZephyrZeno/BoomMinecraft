using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

// Development caller and allocation fixtures only; all guest/runtime work is ASM.
public static class BoomNormalRuntimeResourcesProbe {
    [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
    [DllImport("kernel32.dll")] static extern bool GetProcessAffinityMask(IntPtr h,out UIntPtr process,out UIntPtr system);
    [DllImport("kernel32.dll")] static extern bool SetProcessAffinityMask(IntPtr h,UIntPtr mask);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr cls,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Entry(IntPtr ctx,IntPtr argv);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Kernel(IntPtr ctx,IntPtr argv,IntPtr pool,int op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr heap,ulong bytes,ulong refs,ulong type);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Collect(IntPtr heap,IntPtr roots,ulong count);
    static T Fn<T>(IntPtr m,string n) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(m,n));}
    static void Need(bool b,string s){if(!b)throw new Exception(s);}
    static void Reset(IntPtr c){for(int i=0;i<32;i+=8)Marshal.WriteInt64(c,i,0);Marshal.WriteInt32(c,4,37);Marshal.WriteInt32(c,8,73);}
    static IntPtr Memory(List<IntPtr> a,int n){IntPtr p=Marshal.AllocHGlobal(n);for(int i=0;i<n;i++)Marshal.WriteByte(p,i,0);a.Add(p);return p;}
    static long Query(Entry f,IntPtr c,IntPtr a){Reset(c);long r=f(c,a);Need(Marshal.ReadInt32(c)==0,"Runtime query failed, kind="+Marshal.ReadInt32(c));return r;}
    static int JavaCpu(string java,string classes){
        var start=new ProcessStartInfo(java);start.UseShellExecute=false;start.CreateNoWindow=true;start.RedirectStandardOutput=true;start.RedirectStandardError=true;
        start.ArgumentList.Add("-cp");start.ArgumentList.Add(classes);start.ArgumentList.Add("NormalRuntimeResourcesReference");
        using(var p=Process.Start(start)){
            Need(p!=null,"JVM processor oracle start failed");var output=p.StandardOutput.ReadToEndAsync();var errors=p.StandardError.ReadToEndAsync();
            if(!p.WaitForExit(30000)){p.Kill(true);throw new Exception("Owned JVM oracle timeout");}
            string result=output.GetAwaiter().GetResult(),error=errors.GetAwaiter().GetResult();Need(p.ExitCode==0,"JVM processor oracle failed: "+error);
            foreach(string line in result.Split('\n'))if(line.StartsWith("cpu\t"))return int.Parse(line.Substring(4).Trim());
            throw new Exception("Missing JVM processor oracle result");
        }
    }
    public static long[] Run(string runtime,string image,int classId,string[] names,string java,string oracleClasses){
        IntPtr lib=NativeLibrary.Load(runtime),dll=IntPtr.Zero,heap=IntPtr.Zero;var memory=new List<IntPtr>();var destroy=Fn<Destroy>(lib,"boom_heap_destroy");
        try {
            dll=NativeLibrary.Load(image);heap=Fn<Create>(lib,"boom_heap_create")(64UL*1024*1024);Need(heap!=IntPtr.Zero&&Fn<Bind>(dll,"boom_java_string_literals_bind_heap")(heap)==1,"Runtime source heap bind failed");
            IntPtr cls=NativeLibrary.GetExport(dll,"boom_class"+classId),single=NativeLibrary.GetExport(dll,"boom_s"+classId+"_0"),pool=NativeLibrary.GetExport(dll,"boom_java_runtime_pool");
            IntPtr ctx=Memory(memory,32),argv=Memory(memory,8);var ensure=Fn<Ensure>(lib,"boom_class_ensure32");var kernel=Fn<Kernel>(lib,"boom_runtime_resource");
            var alloc=Fn<Alloc>(lib,"boom_heap_alloc");var collect=Fn<Collect>(lib,"boom_heap_collect");var query=new Entry[4];for(int i=0;i<4;i++)query[i]=Fn<Entry>(dll,names[i]);
            Need(Marshal.ReadInt32(cls,8)==0&&Marshal.ReadIntPtr(single)==IntPtr.Zero,"Runtime singleton was preinitialized");
            const int workers=8,iterations=1024;
            using(var barrier=new Barrier(workers))Parallel.For(0,workers,w=>{
                IntPtr c=Marshal.AllocHGlobal(32);try{Reset(c);barrier.SignalAndWait();Need(ensure(cls,c)==0&&Marshal.ReadInt32(c)==0,"Original Runtime initializer failed");}finally{Marshal.FreeHGlobal(c);}
            });
            IntPtr receiver=Marshal.ReadIntPtr(single);Need(Marshal.ReadInt32(cls,8)==2&&receiver!=IntPtr.Zero,"Original Runtime constructor/singleton was not published");Marshal.WriteIntPtr(argv,receiver);
            long capacity=Marshal.ReadInt64(heap,16),before=Query(query[1],ctx,argv);
            Need(capacity>0&&before==capacity-Marshal.ReadInt64(heap,48)&&Query(query[2],ctx,argv)==capacity&&Query(query[3],ctx,argv)==capacity,"Native heap capacity/counters differ");
            for(int i=0;i<32;i++)Need(alloc(heap,(ulong)(1024+i*17),0,264)!=IntPtr.Zero,"Memory fixture allocation failed");
            long after=Query(query[1],ctx,argv);Need(after<before&&after==capacity-Marshal.ReadInt64(heap,48),"freeMemory ignored occupied block spans");
            Need(Query(query[2],ctx,argv)==capacity&&Query(query[3],ctx,argv)==capacity,"Fixed arena capacity changed on allocation");
            IntPtr roots=Memory(memory,8);Marshal.WriteIntPtr(roots,receiver);long freed=collect(heap,roots,1);
            Need(freed==32&&Query(query[1],ctx,argv)==before&&Marshal.ReadIntPtr(single)==receiver,"Quiescent fixture collection/counter recovery failed");
            Need(alloc(heap,(ulong)capacity+1,0,264)==IntPtr.Zero&&Query(query[1],ctx,argv)==before,"Over-budget fixture allocation changed accounting");
            Parallel.For(0,workers,w=>{
                IntPtr c=Marshal.AllocHGlobal(32),a=Marshal.AllocHGlobal(8);try{
                    Marshal.WriteIntPtr(a,receiver);
                    for(int i=0;i<iterations;i++){
                        if((i&7)==0)Need(alloc(heap,128,0,264)!=IntPtr.Zero,"Parallel fixture allocation failed");
                        long free=Query(query[1],c,a);Need(free>=0&&free<=capacity&&Query(query[2],c,a)==capacity&&Query(query[3],c,a)==capacity&&Query(query[0],c,a)>0,"Concurrent Runtime query invariant failed");
                    }
                }finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}
            });
            int affinityCases=0;IntPtr process=GetCurrentProcess();Need(GetProcessAffinityMask(process,out UIntPtr original,out UIntPtr system),"Own process affinity read failed");
            ulong mask=original.ToUInt64();
            if(mask!=0){
                ulong first=mask&unchecked(0UL-mask),rest=mask&~first,second=rest&unchecked(0UL-rest);var masks=new HashSet<ulong>{first,first|second,mask};
                try{foreach(ulong selected in masks){
                    Need(SetProcessAffinityMask(process,new UIntPtr(selected)),"Own test process affinity change failed");
                    int expected=JavaCpu(java,oracleClasses);long actual=Query(query[0],ctx,argv);Need(actual==expected&&actual>0,"ASM/JVM process-affinity processor counts differ");affinityCases++;
                }}finally{Need(SetProcessAffinityMask(process,original),"Own test process affinity restore failed");}
            }else{Need(Query(query[0],ctx,argv)==JavaCpu(java,oracleClasses),"Default group CPU oracle differs");affinityCases++;}
            int errors=0;
            Marshal.WriteIntPtr(argv,IntPtr.Zero);Reset(ctx);Need(query[3](ctx,argv)==0&&Marshal.ReadInt32(ctx)==4,"Null Runtime receiver accepted");errors++;
            IntPtr wrong=alloc(heap,8,0,264);Marshal.WriteIntPtr(argv,wrong);Reset(ctx);Need(query[3](ctx,argv)==0&&Marshal.ReadInt32(ctx)==7,"Wrong normal receiver accepted");errors++;
            Marshal.WriteIntPtr(argv,receiver);Reset(ctx);Marshal.WriteInt32(ctx,99);long used=Marshal.ReadInt64(heap,48);
            Need(query[3](ctx,argv)==0&&Marshal.ReadInt32(ctx)==99&&Marshal.ReadInt32(ctx,4)==37&&Marshal.ReadInt64(heap,48)==used,"Pending resource error overwritten");errors++;
            Need(kernel(IntPtr.Zero,argv,pool,3)==0,"Null resource context accepted");errors++;
            Reset(ctx);Need(kernel(ctx,IntPtr.Zero,pool,3)==0&&Marshal.ReadInt32(ctx)==7,"Null resource arguments accepted");errors++;
            Reset(ctx);Need(kernel(ctx,argv,pool,99)==0&&Marshal.ReadInt32(ctx)==7,"Unknown resource operation accepted");errors++;
            byte[] bytes=new byte[64];Marshal.Copy(pool,bytes,0,64);IntPtr copy=Memory(memory,64);
            foreach(int offset in new[]{0,4,32,40,48,56}){
                Marshal.Copy(bytes,0,copy,64);Marshal.WriteInt32(copy,offset,12345);Reset(ctx);Need(kernel(ctx,argv,copy,3)==0&&Marshal.ReadInt32(ctx)==7,"Invalid resource pool accepted: "+offset);errors++;
            }
            foreach(int offset in new[]{8,16,24}){
                Marshal.Copy(bytes,0,copy,64);Marshal.WriteIntPtr(copy,offset,IntPtr.Zero);Reset(ctx);Need(kernel(ctx,argv,copy,3)==0&&Marshal.ReadInt32(ctx)==7,"Missing resource metadata accepted: "+offset);errors++;
            }
            Need(Marshal.ReadInt32(NativeLibrary.GetExport(dll,"boom_diagnostic_pool"),8)==0,"Runtime-only probe reached an unimplemented source dependency");
            return new long[]{workers,workers*iterations*4,affinityCases,errors,freed,capacity,Marshal.ReadInt64(heap,48)};
        }finally{if(heap!=IntPtr.Zero)Need(destroy(heap)==1,"Runtime heap cleanup failed");for(int i=memory.Count-1;i>=0;i--)Marshal.FreeHGlobal(memory[i]);if(dll!=IntPtr.Zero)NativeLibrary.Free(dll);NativeLibrary.Free(lib);}
    }
}
