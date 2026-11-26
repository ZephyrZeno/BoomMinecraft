// FFI and assertions only. Java allocation, construction, throw, trace capture,
// class initialization, native registration and synchronization execute ASM.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading.Tasks;
public static class BoomNormalNativeSourceProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr state,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Entry(IntPtr ctx,IntPtr args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Service(IntPtr ctx,IntPtr args,IntPtr pool,int op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Release();
    static T Fn<T>(IntPtr dll,string name)where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(dll,name));}
    static void Need(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Reset(IntPtr p){for(int i=0;i<32;i+=8)Marshal.WriteInt64(p,i,0);}
    static int I(JsonElement e,string n){return e.GetProperty(n).GetInt32();}
    public static long[] Run(string configuration){
        using var doc=JsonDocument.Parse(File.ReadAllText(configuration));var s=doc.RootElement;
        var lib=NativeLibrary.Load(s.GetProperty("runtime").GetString());var image=NativeLibrary.Load(s.GetProperty("image").GetString());
        IntPtr heap=IntPtr.Zero,ctx=Marshal.AllocHGlobal(32),args=Marshal.AllocHGlobal(16);bool success=false;
        IntPtr Export(string n){return NativeLibrary.GetExport(image,n);}
        string Stop(IntPtr c){return " kind="+Marshal.ReadInt32(c)+" method="+Marshal.ReadInt32(c,8)+" pc="+Marshal.ReadInt32(c,4)+" stop="+Marshal.ReadInt32(Export("boom_diagnostic_pool"),32);}
        try{
            Reset(ctx);Marshal.WriteInt64(args,0);Marshal.WriteInt64(args,8,0);heap=Fn<Create>(lib,"boom_heap_create")(128UL*1024*1024);
            Need(heap!=IntPtr.Zero&&Fn<Bind>(image,"boom_java_string_literals_bind_heap")(heap)==1,"Normal source heap binding failed");
            var ensure=Fn<Ensure>(lib,"boom_class_ensure32");foreach(var r in s.GetProperty("roots").EnumerateArray())Need(ensure(Export("boom_class"+r.GetInt32()),ctx)==0&&Marshal.ReadInt32(ctx)==0,"Normal source prerequisite failed"+Stop(ctx));
            var classPool=Export("boom_java_class_pool");var typeMap=Marshal.ReadIntPtr(classPool,40);var typeRows=Marshal.ReadIntPtr(typeMap,16);var layouts=new Dictionary<int,IntPtr>();
            for(int i=0;i<Marshal.ReadInt32(typeMap,8);i++){var row=IntPtr.Add(typeRows,40*i);if(Marshal.ReadInt32(row,20)==0)layouts.Add(Marshal.ReadInt32(row,16),Marshal.ReadIntPtr(row));}
            IntPtr Layout(int id){Need(layouts.TryGetValue(id,out var value),"Normal source layout is missing: "+id);return value;}
            var owner=Export("boom_class"+I(s,"owner_class"));Need(Marshal.ReadInt32(owner,8)==0,"Normal native owner was already initialized");
            long[] values;
            if(s.GetProperty("mode").GetString()=="scoped-memory"){
                var entry=Fn<Entry>(image,s.GetProperty("native_symbol").GetString());
                var buffer=Export("boom_class"+I(s,"buffer_class"));var bufferScoped=Export(s.GetProperty("buffer_scoped_access").GetString());
                Need(Marshal.ReadInt32(buffer,8)==0&&Marshal.ReadIntPtr(bufferScoped)==IntPtr.Zero,"Original Buffer prerequisite was already initialized");
                var pool=Export(s.GetProperty("pool").GetString());Need(Marshal.ReadInt32(pool,8)==0&&Marshal.ReadIntPtr(pool,16)==IntPtr.Zero,"Scoped registration was already published");
                const int coldWorkers=8;
                Parallel.For(0,coldWorkers,w=>{var c=Marshal.AllocHGlobal(32);var a=Marshal.AllocHGlobal(16);try{Reset(c);Marshal.WriteInt64(a,0);Marshal.WriteInt64(a,8,0);Need(entry(c,a)==IntPtr.Zero&&Marshal.ReadInt32(c)==0,"Concurrent original ScopedMemoryAccess cold initializer failed"+Stop(c));}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});
                Need(Marshal.ReadInt32(owner,8)==2&&Marshal.ReadInt32(pool,8)==2&&Marshal.ReadInt32(pool,12)==1,"Scoped registration/class initialization did not publish");
                var singleton=Marshal.ReadIntPtr(Export(s.GetProperty("singleton").GetString()));var unsafeObject=Marshal.ReadIntPtr(Export(s.GetProperty("unsafe").GetString()));
                Need(singleton!=IntPtr.Zero&&Marshal.ReadIntPtr(singleton,-8)==Layout(I(s,"owner_class")),"Original scoped singleton constructor differs");
                Need(unsafeObject!=IntPtr.Zero&&Marshal.ReadIntPtr(unsafeObject,-8)==Layout(I(s,"unsafe_class")),"Original scoped Unsafe prerequisite differs");
                Need(ensure(buffer,ctx)==0&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt32(buffer,8)==2&&Marshal.ReadIntPtr(bufferScoped)==singleton,"Original Buffer initializer did not obtain the scoped singleton through its Java getter"+Stop(ctx));
                Need(Marshal.ReadIntPtr(pool,16)==NativeLibrary.GetExport(lib,"boom_scoped_close_unavailable"),"Unavailable close target was silently replaced");
                var service=Fn<Service>(image,s.GetProperty("service").GetString());var copy=Marshal.AllocHGlobal(32);int errors=0;
                try{
                    void Copy(){for(int i=0;i<32;i+=8)Marshal.WriteInt64(copy,i,Marshal.ReadInt64(pool,i));Marshal.WriteInt32(copy,8,0);Reset(ctx);}
                    foreach(int variant in new[]{0,1,2,3,4,5,6,7,8}){
                        Copy();int op=0;var selectedPool=copy;
                        switch(variant){case 0:Marshal.WriteInt32(copy,0);break;case 1:Marshal.WriteInt32(copy,4,2);break;case 2:Marshal.WriteInt32(copy,12,2);break;case 3:Marshal.WriteInt64(copy,24,1);break;case 4:Marshal.WriteIntPtr(copy,16,new IntPtr(1));break;case 5:Marshal.WriteInt32(copy,8,1);break;case 6:op=1;break;case 7:Marshal.WriteInt32(copy,8,2);Marshal.WriteIntPtr(copy,16,IntPtr.Zero);break;case 8:selectedPool=IntPtr.Zero;break;}
                        Need(service(ctx,args,selectedPool,op)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7,"Malformed scoped registration was accepted");errors++;
                    }
                    Copy();Marshal.WriteInt32(ctx,16);Marshal.WriteInt32(ctx,4,91);Marshal.WriteInt64(ctx,16,123);
                    Need(service(ctx,args,copy,0)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==16&&Marshal.ReadInt32(ctx,4)==91&&Marshal.ReadInt64(ctx,16)==123&&Marshal.ReadInt32(copy,8)==0,"Scoped registration changed an existing exception");errors++;
                }finally{Marshal.FreeHGlobal(copy);Reset(ctx);}
                const int workers=8,iterations=1024;
                Parallel.For(0,workers,w=>{var c=Marshal.AllocHGlobal(32);var a=Marshal.AllocHGlobal(16);try{Reset(c);Marshal.WriteInt64(a,0);Marshal.WriteInt64(a,8,0);for(int i=0;i<iterations;i++)Need(entry(c,a)==IntPtr.Zero&&Marshal.ReadIntPtr(bufferScoped)==singleton&&Marshal.ReadInt32(c)==0,"Concurrent original scoped registration failed"+Stop(c));}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});
                values=new long[]{1,1,errors,workers,workers*iterations,1,coldWorkers};
            }else{
                var caller=Fn<Entry>(image,s.GetProperty("caller").GetString());var fields=s.GetProperty("exception_fields");var constructor=s.GetProperty("constructor_fields");
                var layout=Layout(I(s,"exception_class"));var trace=Export("boom_trace_pool");var callerRows=Marshal.ReadIntPtr(trace,24);var callerRow=IntPtr.Zero;
                int lo=0,hi=Marshal.ReadInt32(trace,16)-1;while(lo<=hi){int mid=lo+(hi-lo)/2;var row=IntPtr.Add(callerRows,32*mid);int id=Marshal.ReadInt32(row);if(id==I(s,"caller_id")){callerRow=row;break;}if(id<I(s,"caller_id"))lo=mid+1;else hi=mid-1;}
                Need(callerRow!=IntPtr.Zero,"Original source caller frame metadata is missing");
                var unassigned=Export(s.GetProperty("unassigned_stack").GetString());var suppressed=Export(s.GetProperty("suppressed_sentinel").GetString());
                void Check(IntPtr c,IntPtr a){
                    Reset(c);Need(caller(c,a)==IntPtr.Zero&&Marshal.ReadInt32(c)==16,"Original Unsafe helper did not throw its Java IllegalAccessError"+Stop(c));
                    var exception=Marshal.ReadIntPtr(c,16);Need(exception!=IntPtr.Zero&&Marshal.ReadIntPtr(exception,-8)==layout,"Original explicit throw has no normal IllegalAccessError object");
                    Need(Marshal.ReadIntPtr(exception,I(constructor,"cause"))==exception&&Marshal.ReadIntPtr(exception,I(constructor,"detailMessage"))==IntPtr.Zero&&Marshal.ReadIntPtr(exception,I(constructor,"suppressedExceptions"))==Marshal.ReadIntPtr(suppressed),"Original Throwable constructor fields differ");
                    var back=Marshal.ReadIntPtr(exception,I(fields,"backtrace"));int depth=Marshal.ReadInt32(exception,I(fields,"depth"));
                    Need(depth==1&&back!=IntPtr.Zero&&Marshal.ReadIntPtr(exception,I(fields,"stack_trace"))==Marshal.ReadIntPtr(unassigned)&&Marshal.ReadIntPtr(unassigned)!=IntPtr.Zero,"Original Java Throwable trace/sentinel publication differs");
                    Need(Marshal.ReadInt64(back,-8)==267&&Marshal.ReadInt64(back,-16)==24&&Marshal.ReadInt32(back,-20)==0&&Marshal.ReadInt64(back)==0x0000000142545243L&&Marshal.ReadIntPtr(back,8)==trace,"Original Java throw has no valid primitive backtrace");
                    ulong frame=unchecked((ulong)Marshal.ReadInt64(back,16));Need((frame>>32)==(uint)I(s,"caller_id")&&(uint)frame<(uint)Marshal.ReadInt32(callerRow,16),"Backtrace did not record the original Unsafe throw caller and bytecode position");
                }
                Check(ctx,args);Need(Marshal.ReadInt32(owner,8)==2,"Original Throwable class did not initialize");
                const int workers=8,iterations=64;
                Parallel.For(0,workers,w=>{var c=Marshal.AllocHGlobal(32);var a=Marshal.AllocHGlobal(16);try{Marshal.WriteInt64(a,0);Marshal.WriteInt64(a,8,0);for(int i=0;i<iterations;i++)Check(c,a);}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});
                values=new long[]{1,1,workers,workers*iterations};
            }
            Need(Marshal.ReadInt32(Export("boom_diagnostic_pool"),8)==0,"Original native source reached an unavailable dependency"+Stop(ctx));
            success=true;return values;
        }finally{
            if(success)Need(Fn<Release>(image,"boom_release_trace_pool")()==0,"Original native source retained Java frames");
            if(heap!=IntPtr.Zero){int freed=Fn<Destroy>(lib,"boom_heap_destroy")(heap);if(success)Need(freed==1,"Original native source heap cleanup failed");}
            Marshal.FreeHGlobal(args);Marshal.FreeHGlobal(ctx);if(success){NativeLibrary.Free(image);NativeLibrary.Free(lib);}
        }
    }
}
