using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

// Development host only: all selected Java bodies and failure recording run ASM.
public static class BoomDiagnosticStartupHost {
    static bool requiresProcessTeardown;
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int ReleaseFrames();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr cls,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Entry(IntPtr ctx,IntPtr argv);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr New(IntPtr heap,IntPtr layout,IntPtr ctx);
    static T Fn<T>(IntPtr lib,string name) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(lib,name));}
    static void Need(bool ok,string message){if(!ok)throw new Exception(message);}
    public static long[] Run(string runtime,string image,int heapMB,string[] classes,string[] entries,string receiverLayout=null){
        Need(!requiresProcessTeardown,"A stopped diagnostic with held monitors requires a fresh process");
        IntPtr lib=NativeLibrary.Load(runtime),dll=IntPtr.Zero,heap=IntPtr.Zero,argv=IntPtr.Zero,ctx=Marshal.AllocHGlobal(32);
        var destroy=Fn<Destroy>(lib,"boom_heap_destroy");
        try{
            dll=NativeLibrary.Load(image);IntPtr pool=NativeLibrary.GetExport(dll,"boom_diagnostic_pool");
            Need(Marshal.ReadInt32(pool)==0x44535450&&Marshal.ReadInt32(pool,4)==1&&Marshal.ReadInt32(pool,8)==0,"Diagnostic image was reused/preinitialized");
            for(int i=0;i<32;i+=8)Marshal.WriteInt64(ctx,i,0);
            heap=Fn<Create>(lib,"boom_heap_create")(checked((ulong)heapMB*1024*1024));
            Need(heap!=IntPtr.Zero&&Fn<Bind>(dll,"boom_java_string_literals_bind_heap")(heap)==1,"Diagnostic heap bind failed");
            var ensure=Fn<Ensure>(lib,"boom_class_ensure32");int initialized=0,called=0;long returnValue=0;
            if(!string.IsNullOrEmpty(receiverLayout)){IntPtr receiver=Fn<New>(lib,"boom_object_new")(heap,NativeLibrary.GetExport(dll,receiverLayout),ctx);Need(receiver!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Prepared receiver shape allocation failed");argv=Marshal.AllocHGlobal(8);Marshal.WriteIntPtr(argv,receiver);}
            // Check cold preparation before any root executes. One root can
            // legitimately initialize a later requested root as a dependency.
            foreach(string cls in classes)Need(Marshal.ReadInt32(NativeLibrary.GetExport(dll,cls),8)==0,"Root class was preinitialized");
            foreach(string cls in classes){
                IntPtr descriptor=NativeLibrary.GetExport(dll,cls);
                int result=ensure(descriptor,ctx);
                if(result!=0||Marshal.ReadInt32(ctx)!=0||Marshal.ReadInt32(pool,8)!=0)break;
                Need(Marshal.ReadInt32(descriptor,8)==2,"Original class initializer was not published");initialized++;
            }
            if(Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt32(pool,8)==0)foreach(string entry in entries){
                returnValue=Fn<Entry>(dll,entry)(ctx,argv);called++;
                if(Marshal.ReadInt32(ctx)!=0||Marshal.ReadInt32(pool,8)!=0)break;
            }
            long held=Marshal.ReadInt64(heap,112);int registryLock=Marshal.ReadInt32(heap,104);
            var result_=new long[]{Marshal.ReadInt32(ctx),Marshal.ReadInt32(ctx,4),Marshal.ReadInt32(ctx,8),Marshal.ReadInt32(ctx,12),
                Marshal.ReadInt32(pool,8),Marshal.ReadInt32(pool,32),Marshal.ReadInt32(pool,44),Marshal.ReadInt32(pool,48),
                Marshal.ReadInt32(pool,52),initialized,called,Marshal.ReadInt64(heap,56),returnValue,0,held,registryLock};
            int freed=destroy(heap);
            if(freed!=1){
                // A noncatchable diagnostic abort skips bytecode finally blocks.
                // Do not force-unlock monitors or pretend guest cleanup ran. The
                // parent owns this one-shot process; OS teardown reclaims it.
                Need(result_[0]==0xB001&&result_[4]==2&&held>0&&registryLock==0&&
                    Marshal.ReadInt32(heap)==0x48454150&&Marshal.ReadInt32(heap,4)==1,
                    "Diagnostic heap cleanup failed outside a recorded stop: kind="+result_[0]+", method="+result_[2]+", pc="+result_[1]+", held="+held+", registryLock="+registryLock);
                requiresProcessTeardown=true;
            }
            result_[13]=freed==1?1:0;heap=IntPtr.Zero;return result_;
        }finally{if(heap!=IntPtr.Zero)destroy(heap);if(argv!=IntPtr.Zero)Marshal.FreeHGlobal(argv);Marshal.FreeHGlobal(ctx);if(dll!=IntPtr.Zero){
            IntPtr frameRelease;if(NativeLibrary.TryGetExport(dll,"boom_release_trace_pool",out frameRelease))Need(Marshal.GetDelegateForFunctionPointer<ReleaseFrames>(frameRelease)()==0,"Diagnostic image still owns active Java frames");
            NativeLibrary.Free(dll);
        }NativeLibrary.Free(lib);}
    }
}
