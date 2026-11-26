using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

// Development caller. Integer slots avoid changing NaN payloads in the host FPU.
public static class BoomNormalBitcastsProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr cls,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(IntPtr ctx,IntPtr argv);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Kernel(IntPtr ctx,IntPtr argv,IntPtr pool,int op);
    static T Fn<T>(IntPtr m,string n) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(m,n));}
    static void Need(bool b,string s){if(!b)throw new Exception(s);}
    static void Reset(IntPtr c){for(int i=0;i<32;i+=8)Marshal.WriteInt64(c,i,0);Marshal.WriteInt32(c,4,37);Marshal.WriteInt32(c,8,73);}
    static IntPtr Memory(List<IntPtr> a,int n){IntPtr p=Marshal.AllocHGlobal(n);for(int i=0;i<n;i++)Marshal.WriteByte(p,i,0);a.Add(p);return p;}
    static ulong RandomBits(ref ulong x){x^=x<<13;x^=x>>7;x^=x<<17;return x;}
    public static int WriteCases(string path){
        var f=new HashSet<ulong>{0,0x80000000,1,0x80000001,0x007fffff,0x807fffff,0x00800000,0x80800000,0x3f800000,0xbf800000,0x7f7fffff,0xff7fffff,0x7f800000,0xff800000,0x7fc00000,0xffc00000,0x7fc12345,0xffc12345,0x7f800001,0xff800001,0x7fffffff,0xffffffff};
        var d=new HashSet<ulong>{0,0x8000000000000000,1,0x8000000000000001,0x000fffffffffffff,0x800fffffffffffff,0x0010000000000000,0x8010000000000000,0x3ff0000000000000,0xbff0000000000000,0x7fefffffffffffff,0xffefffffffffffff,0x7ff0000000000000,0xfff0000000000000,0x7ff8000000000000,0xfff8000000000000,0x7ff8123456789abc,0xfff8123456789abc,0x7ff0000000000001,0xfff0000000000001,0x7fffffffffffffff,0xffffffffffffffff};
        ulong state=0x104b17ca57;
        for(int i=0;i<4096;i++){f.Add((uint)RandomBits(ref state));d.Add(RandomBits(ref state));}
        using(var w=new StreamWriter(path)){foreach(ulong v in f)w.WriteLine("F\t"+v.ToString("x8"));foreach(ulong v in d)w.WriteLine("D\t"+v.ToString("x16"));}
        return f.Count+d.Count;
    }
    static ulong Query(Entry f,IntPtr c,IntPtr a,ulong bits){Marshal.WriteInt64(a,unchecked((long)bits));Reset(c);ulong r=f(c,a);Need(Marshal.ReadInt32(c)==0,"Bitcast entry failed");return r;}
    public static int KernelCases(string runtime,string cases){
        IntPtr lib=NativeLibrary.Load(runtime);var memory=new List<IntPtr>();
        try{
            IntPtr c=Memory(memory,32),a=Memory(memory,8),pool=Memory(memory,16);Marshal.WriteInt32(pool,0,0x54534342);Marshal.WriteInt32(pool,4,1);Marshal.WriteInt32(pool,8,4);
            var kernel=Fn<Kernel>(lib,"boom_java_bitcast");int calls=0;
            foreach(string line in File.ReadLines(cases)){
                string[] p=line.Split('\t');bool single=p[0]=="F";ulong v=Convert.ToUInt64(p[1],16);Marshal.WriteInt64(a,unchecked((long)(single?v|0xa5a5a5a500000000UL:v)));
                for(int op=single?0:2;op<(single?2:4);op++){Reset(c);Need(kernel(c,a,pool,op)==v&&Marshal.ReadInt32(c)==0,"Kernel-only bit pattern mismatch");calls++;}
            }
            return calls;
        }finally{for(int i=memory.Count-1;i>=0;i--)Marshal.FreeHGlobal(memory[i]);NativeLibrary.Free(lib);}
    }
    public static long[] Run(string runtime,string image,string oracle,string[] names,int[] classes,int[] typeFields){
        IntPtr lib=NativeLibrary.Load(runtime),dll=IntPtr.Zero,heap=IntPtr.Zero;var memory=new List<IntPtr>();var destroy=Fn<Destroy>(lib,"boom_heap_destroy");
        try{
            dll=NativeLibrary.Load(image);heap=Fn<Create>(lib,"boom_heap_create")(64UL*1024*1024);Need(heap!=IntPtr.Zero&&Fn<Bind>(dll,"boom_java_string_literals_bind_heap")(heap)==1,"Bitcast source heap bind failed");
            IntPtr ctx=Memory(memory,32),args=Memory(memory,8),pool=NativeLibrary.GetExport(dll,"boom_java_bitcast_pool");var ensure=Fn<Ensure>(lib,"boom_class_ensure32");var kernel=Fn<Kernel>(lib,"boom_java_bitcast");
            var entries=new Entry[4];for(int i=0;i<4;i++)entries[i]=Fn<Entry>(dll,names[i]);
            const int workers=8,iterations=2048;
            for(int i=0;i<classes.Length;i++){
                IntPtr cls=NativeLibrary.GetExport(dll,"boom_class"+classes[i]),cell=NativeLibrary.GetExport(dll,"boom_s"+classes[i]+"_"+typeFields[i]);
                Need(Marshal.ReadInt32(cls,8)==0&&Marshal.ReadIntPtr(cell)==IntPtr.Zero,"Numeric source class was preinitialized");
            }
            using(var barrier=new Barrier(workers))Parallel.For(0,workers,w=>{
                IntPtr c=Marshal.AllocHGlobal(32);try{barrier.SignalAndWait();foreach(int id in classes){Reset(c);Need(ensure(NativeLibrary.GetExport(dll,"boom_class"+id),c)==0&&Marshal.ReadInt32(c)==0,"Original numeric initializer failed");}}finally{Marshal.FreeHGlobal(c);}
            });
            for(int i=0;i<classes.Length;i++)Need(Marshal.ReadIntPtr(NativeLibrary.GetExport(dll,"boom_s"+classes[i]+"_"+typeFields[i]))!=IntPtr.Zero,"Original numeric TYPE mirror missing");
            int cases=0,strict=0,variations=0;long nativeCalls=0;
            foreach(string line in File.ReadLines(oracle)){
                string[] p=line.Split('\t');Need(p.Length==4,"Malformed bitcast JVM oracle");bool single=p[0]=="F";ulong value=Convert.ToUInt64(p[1],16),observed=Convert.ToUInt64(p[2],16),canonical=Convert.ToUInt64(p[3],16);
                bool nan=single?(value&0x7fffffffUL)>0x7f800000UL:(value&0x7fffffffffffffffUL)>0x7ff0000000000000UL;
                bool signaling=nan&&(value&(single?0x00400000UL:0x0008000000000000UL))==0;
                ulong expectedCanonical=nan?(single?0x7fc00000UL:0x7ff8000000000000UL):value;
                Need(canonical==expectedCanonical,"JVM canonical NaN oracle differs");
                if(!signaling){Need(observed==value,"JVM changed non-signaling bit pattern");strict++;}else if(observed!=value)variations++;
                int op=single?0:2;ulong input=single?0xa5a5a5a500000000UL|value:value;
                Need(Query(entries[op],ctx,args,input)==value,"Raw forward bit pattern changed");nativeCalls++;
                ulong inverse=Query(entries[op+1],ctx,args,input);nativeCalls++;Need(inverse==value,"Raw inverse bit pattern changed");
                Need(Query(entries[op],ctx,args,inverse)==value,"Managed-slot raw roundtrip failed");nativeCalls++;cases++;
            }
            Parallel.For(0,workers,w=>{
                IntPtr c=Marshal.AllocHGlobal(32),a=Marshal.AllocHGlobal(8);ulong state=(ulong)(w+104);try{
                    for(int i=0;i<iterations;i++){ulong v=RandomBits(ref state);Need(Query(entries[0],c,a,v)==(uint)v&&Query(entries[1],c,a,v)==(uint)v&&Query(entries[2],c,a,v)==v&&Query(entries[3],c,a,v)==v,"Concurrent bitcast width/payload mismatch");}
                }finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}
            });
            int errors=0;Marshal.WriteInt64(args,123);Reset(ctx);Marshal.WriteInt32(ctx,99);long allocated=Marshal.ReadInt64(heap,56);
            Need(entries[0](ctx,args)==0&&Marshal.ReadInt32(ctx)==99&&Marshal.ReadInt32(ctx,4)==37&&Marshal.ReadInt64(heap,56)==allocated,"Pending bitcast error overwritten");errors++;
            Need(kernel(IntPtr.Zero,args,pool,0)==0,"Null bitcast context accepted");errors++;
            Reset(ctx);Need(kernel(ctx,IntPtr.Zero,pool,0)==0&&Marshal.ReadInt32(ctx)==7,"Null bitcast args accepted");errors++;
            Reset(ctx);Need(kernel(ctx,args,IntPtr.Zero,0)==0&&Marshal.ReadInt32(ctx)==7,"Null bitcast pool accepted");errors++;
            Reset(ctx);Need(kernel(ctx,args,pool,4)==0&&Marshal.ReadInt32(ctx)==7,"Unknown bitcast operation accepted");errors++;
            byte[] bytes=new byte[16];Marshal.Copy(pool,bytes,0,16);IntPtr copy=Memory(memory,16);
            foreach(int offset in new[]{0,4,8,12}){Marshal.Copy(bytes,0,copy,16);Marshal.WriteInt32(copy,offset,12345);Reset(ctx);Need(kernel(ctx,args,copy,0)==0&&Marshal.ReadInt32(ctx)==7,"Bad bitcast metadata accepted: "+offset);errors++;}
            Need(Marshal.ReadInt32(NativeLibrary.GetExport(dll,"boom_diagnostic_pool"),8)==0,"Bitcast probe reached an unimplemented source dependency");
            return new long[]{workers,workers*iterations*4,cases,strict,variations,nativeCalls,errors};
        }finally{if(heap!=IntPtr.Zero)Need(destroy(heap)==1,"Bitcast heap cleanup failed");for(int i=memory.Count-1;i>=0;i--)Marshal.FreeHGlobal(memory[i]);if(dll!=IntPtr.Zero)NativeLibrary.Free(dll);NativeLibrary.Free(lib);}
    }
}
