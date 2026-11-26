using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

// Only FFI/fixture orchestration. The original CDS clinit/getters and services are ASM.
public static class BoomNormalCdsProviderProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr cls,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(IntPtr ctx,IntPtr argv);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Service(IntPtr ctx,IntPtr argv,IntPtr pool,int op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Mirror(IntPtr ctx,IntPtr pool,uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint TypeId(IntPtr ctx,IntPtr pool,IntPtr value);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Release();
    static T Fn<T>(IntPtr lib,string name) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(lib,name));}
    static void Need(bool ok,string message){if(!ok)throw new Exception(message);}
    static IntPtr Memory(List<IntPtr> list,int bytes){var p=Marshal.AllocHGlobal(bytes);for(int i=0;i<bytes;i++)Marshal.WriteByte(p,i,0);list.Add(p);return p;}
    static void Reset(IntPtr c){for(int i=0;i<32;i+=8)Marshal.WriteInt64(c,i,0);}
    public static long[] Run(string runtime,string image,int classId,int cdsId,int coldId,string emptyField,string[] getters,string[] natives){
        var lib=NativeLibrary.Load(runtime);var dll=NativeLibrary.Load(image);var owned=new List<IntPtr>();IntPtr heap=IntPtr.Zero;
        var destroy=Fn<Destroy>(lib,"boom_heap_destroy");
        try {
            var ctx=Memory(owned,32);var args=Memory(owned,8);heap=Fn<Create>(lib,"boom_heap_create")(128UL*1024*1024);
            Need(heap!=IntPtr.Zero&&Fn<Bind>(dll,"boom_java_string_literals_bind_heap")(heap)==1,"CDS fixture heap binding failed");
            var ensure=Fn<Ensure>(lib,"boom_class_ensure32");var classDescriptor=NativeLibrary.GetExport(dll,"boom_class"+classId);
            Need(ensure(classDescriptor,ctx)==0&&Marshal.ReadInt32(ctx)==0,"Original Class initialization failed");
            var descriptor=NativeLibrary.GetExport(dll,"boom_class"+cdsId);Need(Marshal.ReadInt32(descriptor,8)==0,"CDS was preinitialized");
            const int workers=8,iterations=1024;
            using(var barrier=new Barrier(workers))Parallel.For(0,workers,w=>{
                IntPtr c=Marshal.AllocHGlobal(32);try{Reset(c);barrier.SignalAndWait();Need(ensure(descriptor,c)==0&&Marshal.ReadInt32(c)==0,"Cold original CDS initialization failed, kind="+Marshal.ReadInt32(c));}
                finally{Marshal.FreeHGlobal(c);}
            });
            Need(Marshal.ReadInt32(descriptor,8)==2,"Original CDS initializer did not publish");
            var functions=new Entry[5];for(int i=0;i<5;i++)functions[i]=Fn<Entry>(dll,natives[i]);
            foreach(var name in getters)Need(Fn<Entry>(dll,name)(ctx,IntPtr.Zero)==0&&Marshal.ReadInt32(ctx)==0,"Original CDS getter differs");
            for(int i=1;i<5;i++)Need(functions[i](ctx,IntPtr.Zero)==0&&Marshal.ReadInt32(ctx)==0,"Source CDS native policy differs");
            var cold=NativeLibrary.GetExport(dll,"boom_class"+coldId);Need(Marshal.ReadInt32(cold,8)==0,"Cold target initialized by fixture selection");
            var classPool=NativeLibrary.GetExport(dll,"boom_java_class_pool");IntPtr mirror=Fn<Mirror>(lib,"boom_java_class_load")(ctx,classPool,(uint)coldId);
            Need(mirror!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0&&Fn<TypeId>(lib,"boom_java_class_typeid")(ctx,classPool,mirror)==(uint)coldId,"Canonical normal Class mirror failed");
            Marshal.WriteIntPtr(args,mirror);Need(functions[0](ctx,args)==0&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt32(cold,8)==0,"No-archive service initialized or changed target");
            var emptyCell=NativeLibrary.GetExport(dll,emptyField);Need(Marshal.ReadIntPtr(emptyCell)==IntPtr.Zero,"Cold target static reference already populated");
            Need(ensure(cold,ctx)==0&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt32(cold,8)==2,"Original Optional initializer did not run");
            var empty=Marshal.ReadIntPtr(emptyCell);Need(empty!=IntPtr.Zero,"Original Optional EMPTY was not created");
            Need(functions[0](ctx,args)==0&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt32(cold,8)==2&&Marshal.ReadIntPtr(emptyCell)==empty,"No-archive call changed initialized Java state");
            int checks=0;var service=Fn<Service>(dll,"boom_provider_cds_service");var profile=NativeLibrary.GetExport(dll,"boom_provider_cds_pool");var copy=Memory(owned,32);byte[] bytes=new byte[32];Marshal.Copy(profile,bytes,0,32);
            foreach(int offset in new[]{0,4,8,12,16,24}){
                Marshal.Copy(bytes,0,copy,32);Marshal.WriteInt32(copy,offset,offset==16?0:123);Reset(ctx);
                if(offset==16)Marshal.WriteIntPtr(copy,16,IntPtr.Zero);
                Need(service(ctx,args,copy,1)==0&&Marshal.ReadInt32(ctx)==7,"Invalid provider profile accepted: "+offset);checks++;
            }
            Reset(ctx);Need(service(ctx,args,profile,5)==0&&Marshal.ReadInt32(ctx)==7,"Unknown CDS operation accepted");checks++;
            Reset(ctx);Need(service(ctx,IntPtr.Zero,profile,0)==0&&Marshal.ReadInt32(ctx)==7,"Null argv accepted");checks++;
            Reset(ctx);Marshal.WriteIntPtr(args,IntPtr.Zero);Need(service(ctx,args,profile,0)==0&&Marshal.ReadInt32(ctx)!=0,"Null Class accepted");checks++;
            Reset(ctx);Marshal.WriteInt32(ctx,66);Need(service(ctx,args,copy,1)==0&&Marshal.ReadInt32(ctx)==66,"Existing error overwritten");checks++;
            Reset(ctx);Marshal.WriteIntPtr(args,mirror);long before=Marshal.ReadInt64(heap,48);
            Parallel.For(0,workers,w=>{
                IntPtr c=Marshal.AllocHGlobal(32);try{Reset(c);for(int j=0;j<iterations;j++)for(int op=1;op<5;op++)Need(functions[op](c,IntPtr.Zero)==0&&Marshal.ReadInt32(c)==0,"Concurrent source CDS policy failed");}
                finally{Marshal.FreeHGlobal(c);}
            });
            Need(Marshal.ReadInt64(heap,48)==before,"Warm CDS queries allocated guest objects");
            Need(Marshal.ReadInt32(NativeLibrary.GetExport(dll,"boom_diagnostic_pool"),8)==0,"CDS source probe reached an unsupported dependency");
            return new long[]{workers,workers*iterations*4,checks,getters.Length,5,1};
        }finally{
            Need(Fn<Release>(dll,"boom_release_trace_pool")()==0,"CDS image retained Java frames");
            if(heap!=IntPtr.Zero)Need(destroy(heap)==1,"CDS fixture heap teardown failed");
            foreach(var p in owned)Marshal.FreeHGlobal(p);NativeLibrary.Free(dll);NativeLibrary.Free(lib);
        }
    }
}
