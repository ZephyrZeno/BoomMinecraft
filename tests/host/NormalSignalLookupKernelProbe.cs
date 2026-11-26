// FFI, source-layout fixtures and assertions only; lookup executes MASM.
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading.Tasks;
public static class BoomNormalSignalLookupKernelProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr New(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr heap,ulong bytes,ulong refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Lookup(IntPtr ctx,IntPtr args,IntPtr pool,int op);
    static T Fn<T>(IntPtr dll,string name)where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(dll,name));}
    static void Need(bool value,string message){if(!value)throw new Exception(message);}
    static void Reset(IntPtr p){for(int i=0;i<32;i+=8)Marshal.WriteInt64(p,i,0);}
    static IntPtr String(IntPtr heap,IntPtr sp,IntPtr ctx,string text,bool wide,New make,Alloc alloc){
        if(text==null)return IntPtr.Zero;
        Reset(ctx);var value=make(heap,Marshal.ReadIntPtr(sp,40),ctx);Need(value!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Normal String fixture allocation failed");
        bool latin=!wide;foreach(char c in text)if(c>255)latin=false;
        var bytes=new byte[text.Length*(latin?1:2)];
        for(int i=0;i<text.Length;i++){bytes[i*(latin?1:2)]=(byte)text[i];if(!latin)bytes[i*2+1]=(byte)(text[i]>>8);}
        var data=alloc(heap,(ulong)bytes.Length,0,264);Need(data!=IntPtr.Zero,"Normal String fixture byte array allocation failed");
        Marshal.Copy(bytes,0,data,bytes.Length);Marshal.WriteIntPtr(value,Marshal.ReadInt32(sp,48),data);Marshal.WriteByte(value,Marshal.ReadInt32(sp,52),(byte)(latin?0:1));return value;
    }
    static int BigInt(byte[] bytes,int offset){return unchecked((int)((uint)bytes[offset]<<24|(uint)bytes[offset+1]<<16|(uint)bytes[offset+2]<<8|bytes[offset+3]));}
    static string Raw(int packed){char c=(char)packed;return (packed>>16) switch {0=>""+c,1=>"I"+c+"T",2=>"ABR"+c,3=>"BR"+c+"AK",4=>"TER"+c,5=>"FP"+c,6=>"SE"+c+"V",_=>"IL"+c};}
    public static long[] Run(string configuration,string kernel,string rawFile,string literalFile){
        using var doc=JsonDocument.Parse(File.ReadAllText(configuration));var s=doc.RootElement;
        var runtime=NativeLibrary.Load(s.GetProperty("runtime").GetString());var image=NativeLibrary.Load(s.GetProperty("image").GetString());var test=NativeLibrary.Load(kernel);
        IntPtr heap=IntPtr.Zero;var ctx=Marshal.AllocHGlobal(32);var args=Marshal.AllocHGlobal(16);
        try{
            heap=Fn<Create>(runtime,"boom_heap_create")(128UL*1024*1024);Need(heap!=IntPtr.Zero&&Fn<Bind>(image,"boom_java_string_literals_bind_heap")(heap)==1,"Normal signal source heap bind failed");
            var sourcePool=NativeLibrary.GetExport(image,"boom_java_string_literal_pool");var poolCopy=NativeLibrary.GetExport(test,"boom_java_string_literal_pool");
            var poolBytes=new byte[80];Marshal.Copy(sourcePool,poolBytes,0,80);Marshal.Copy(poolBytes,0,poolCopy,80);Marshal.WriteIntPtr(NativeLibrary.GetExport(test,"boom_heap_ptr"),heap);
            var pool=NativeLibrary.GetExport(test,"boom_provider_signal_lookup_pool");var lookup=Fn<Lookup>(test,"boom_provider_signal_lookup_service");
            var make=Fn<New>(runtime,"boom_object_new");var alloc=Fn<Alloc>(runtime,"boom_heap_alloc");
            var expectedRaw=File.ReadAllBytes(rawFile);var expectedLiterals=File.ReadAllBytes(literalFile);
            Need(expectedRaw.Length==8*65536&&expectedLiterals.Length==32*8,"JVM signal oracle size differs");
            string[] literals={"ABRT","FPE","SEGV","INT","TERM","BREAK","ILL","","HUP","SIGINT","int","INT\0","\0INT","IN\u0100","TERM ","BREAK\0X","ABRT\ud800","\ud800","\ud83e\uddf1","0","TERM\0more","ILL\udfff","ＦＰＥ","ABRT\u0001","İNT","break","SIGABRT_COMPAT","\0","00000000","SEGV\n","FPE\ud800\udc00",null};
            int literalCases=0,rawCases=0,errors=0;var warm=new IntPtr[7];
            for(int i=0;i<literals.Length;i++)for(int wide=0;wide<2;wide++){
                var value=String(heap,sourcePool,ctx,literals[i],wide!=0,make,alloc);Reset(ctx);Marshal.WriteIntPtr(args,value);long before=Marshal.ReadInt64(heap,56);
                long result=lookup(ctx,args,pool,0);Need(unchecked((int)result)==BigInt(expectedLiterals,i*8)&&Marshal.ReadInt32(ctx)==BigInt(expectedLiterals,i*8+4)&&Marshal.ReadInt64(heap,56)==before,"Normal signal literal differs from JVM: "+i+" wide="+wide);
                if(i<7&&wide==0)warm[i]=value;literalCases++;
            }
            for(int packed=0;packed<expectedRaw.Length;packed++)for(int wide=1;wide>=0;wide--){
                if(wide==0&&(packed&65535)>255)continue;
                var value=String(heap,sourcePool,ctx,Raw(packed),wide!=0,make,alloc);Reset(ctx);Marshal.WriteIntPtr(args,value);long before=Marshal.ReadInt64(heap,56);
                long result=lookup(ctx,args,pool,0);int expected=expectedRaw[packed]==255?-1:expectedRaw[packed];
                Need(unchecked((int)result)==expected&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt64(heap,56)==before,"Normal signal raw UTF16 differs from JVM: "+packed+" wide="+wide);rawCases++;
            }
            Action<int,Func<long>> fail=(kind,call)=>{Reset(ctx);Need(call()==0&&Marshal.ReadInt32(ctx)==kind,"Normal signal invalid input kind differs: "+kind);errors++;};
            Marshal.WriteIntPtr(args,warm[3]);Need(lookup(IntPtr.Zero,IntPtr.Zero,IntPtr.Zero,0)==0,"Null signal context accepted");errors++;
            fail(7,()=>lookup(ctx,IntPtr.Zero,pool,0));fail(7,()=>lookup(ctx,args,IntPtr.Zero,0));fail(7,()=>lookup(ctx,args,pool,1));fail(7,()=>lookup(ctx,args,pool,-1));
            Marshal.WriteIntPtr(args,IntPtr.Zero);fail(4,()=>lookup(ctx,args,pool,0));Marshal.WriteIntPtr(args,new IntPtr(16));fail(7,()=>lookup(ctx,args,pool,0));Marshal.WriteIntPtr(args,warm[3]);
            int oldCoder=Marshal.ReadByte(warm[3],Marshal.ReadInt32(sourcePool,52));Marshal.WriteByte(warm[3],Marshal.ReadInt32(sourcePool,52),2);fail(7,()=>lookup(ctx,args,pool,0));Marshal.WriteByte(warm[3],Marshal.ReadInt32(sourcePool,52),(byte)oldCoder);
            int magic=Marshal.ReadInt32(pool);Marshal.WriteInt32(pool,0);fail(7,()=>lookup(ctx,args,pool,0));Marshal.WriteInt32(pool,magic);
            Reset(ctx);Marshal.WriteInt32(ctx,9);Marshal.WriteInt32(ctx,4,123);Marshal.WriteInt32(ctx,8,456);Marshal.WriteInt32(ctx,12,7);
            Need(lookup(ctx,IntPtr.Zero,IntPtr.Zero,0)==0&&Marshal.ReadInt32(ctx)==9&&Marshal.ReadInt32(ctx,4)==123&&Marshal.ReadInt32(ctx,8)==456&&Marshal.ReadInt32(ctx,12)==7,"Normal signal pending Context changed");errors++;
            int[] numbers={22,8,11,2,15,21,4};const int workers=8,iterations=2048;long baseline=Marshal.ReadInt64(heap,56);
            Parallel.For(0,workers,w=>{var c=Marshal.AllocHGlobal(32);var a=Marshal.AllocHGlobal(16);try{for(int i=0;i<iterations;i++){Reset(c);int at=(i+w)%7;Marshal.WriteIntPtr(a,warm[at]);Need(lookup(c,a,pool,0)==numbers[at]&&Marshal.ReadInt32(c)==0,"Concurrent normal signal lookup differs");}}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});
            Need(Marshal.ReadInt64(heap,56)==baseline,"Signal lookup allocated guest memory");
            return new long[]{literalCases,rawCases,errors,workers,workers*iterations};
        }finally{
            if(heap!=IntPtr.Zero)Need(Fn<Destroy>(runtime,"boom_heap_destroy")(heap)==1,"Normal signal kernel heap cleanup failed");
            Marshal.FreeHGlobal(args);Marshal.FreeHGlobal(ctx);NativeLibrary.Free(test);NativeLibrary.Free(image);NativeLibrary.Free(runtime);
        }
    }
}
