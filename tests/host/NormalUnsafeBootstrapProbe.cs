using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

// Development caller. Source Java initializers, native services and class-state
// synchronization execute ASM; the host never supplies guest implementation.
public static class BoomNormalUnsafeBootstrapProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr cls,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Entry(IntPtr ctx,IntPtr argv);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Kernel(IntPtr ctx,IntPtr argv,IntPtr pool,int op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Constants(IntPtr ctx,IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Mirror(IntPtr ctx,IntPtr pool,int type);
    static T Fn<T>(IntPtr lib,string n) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(lib,n));}
    static void Need(bool b,string s){if(!b)throw new Exception(s);}
    static void Reset(IntPtr c){for(int i=0;i<32;i+=8)Marshal.WriteInt64(c,i,0);Marshal.WriteInt32(c,4,37);Marshal.WriteInt32(c,8,73);}
    static IntPtr Memory(List<IntPtr> m,int n){IntPtr p=Marshal.AllocHGlobal(n);for(int i=0;i<n;i++)Marshal.WriteByte(p,i,0);m.Add(p);return p;}
    public static long[] Run(string runtime,string image,int unsafeId,int constantsId,string[] nativeNames,int[] arrayTypes,int[] expectedScales,string[] staticNames,int[] staticScales,int pageSize){
        IntPtr lib=NativeLibrary.Load(runtime),dll=IntPtr.Zero,heap=IntPtr.Zero;var memory=new List<IntPtr>();
        var destroy=Fn<Destroy>(lib,"boom_heap_destroy");
        try {
            dll=NativeLibrary.Load(image);heap=Fn<Create>(lib,"boom_heap_create")(128UL*1024*1024);
            Need(heap!=IntPtr.Zero&&Fn<Bind>(dll,"boom_java_string_literals_bind_heap")(heap)==1,"Source heap bind failed");
            IntPtr ctx=Memory(memory,32),argv=Memory(memory,16),pool=NativeLibrary.GetExport(dll,"boom_java_unsafe_pool");
            IntPtr cls=NativeLibrary.GetExport(dll,"boom_class"+unsafeId),constants=NativeLibrary.GetExport(dll,"boom_class"+constantsId);
            IntPtr cells=NativeLibrary.GetExport(dll,"boom_java_unsafe_constant_cells"),single=NativeLibrary.GetExport(dll,"boom_s"+unsafeId+"_0");
            var ensure=Fn<Ensure>(lib,"boom_class_ensure32");var kernel=Fn<Kernel>(lib,"boom_java_unsafe");var fill=Fn<Constants>(lib,"boom_java_unsafe_constants");
            var native=new Entry[4];for(int i=0;i<4;i++)native[i]=Fn<Entry>(dll,nativeNames[i]);
            Need(Marshal.ReadInt32(cls,8)==0&&Marshal.ReadInt32(constants,8)==0&&Marshal.ReadInt32(pool,8)==0&&Marshal.ReadIntPtr(single)==IntPtr.Zero,"VM source state was preinitialized");
            for(int i=0;i<5;i++)Need(Marshal.ReadInt64(Marshal.ReadIntPtr(cells,i*8))==0,"VM constant was prefilled");
            Reset(ctx);Need(ensure(constants,ctx)==0&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt32(constants,8)==2,"Original UnsafeConstants initializer failed");
            long[] expected={8,pageSize,0,1,0};for(int i=0;i<5;i++)Need(Marshal.ReadInt64(Marshal.ReadIntPtr(cells,i*8))==expected[i],"VM injected constant differs: "+i);
            Need(Marshal.ReadInt32(cls,8)==0&&Marshal.ReadInt32(pool,8)==0,"Constants hook initialized Unsafe eagerly");
            Reset(ctx);Need(kernel(ctx,argv,pool,3)==0&&Marshal.ReadInt32(ctx)==20,"Unregistered native was accepted");int errors=1;
            const int workers=8,iterations=1024;
            using(var barrier=new Barrier(workers))Parallel.For(0,workers,w=>{
                IntPtr c=Marshal.AllocHGlobal(32);try{Reset(c);barrier.SignalAndWait();Need(ensure(cls,c)==0&&Marshal.ReadInt32(c)==0,"Concurrent original Unsafe initializer failed, kind="+Marshal.ReadInt32(c));}finally{Marshal.FreeHGlobal(c);}
            });
            Need(Marshal.ReadInt32(cls,8)==2&&Marshal.ReadInt32(pool,8)==2&&Marshal.ReadIntPtr(single)!=IntPtr.Zero,"Unsafe source singleton/readiness was not published");
            for(int i=0;i<staticNames.Length;i++)Need(Marshal.ReadInt32(NativeLibrary.GetExport(dll,staticNames[i]))==staticScales[i],"Original Unsafe array/address static differs: "+staticNames[i]);
            Marshal.WriteIntPtr(argv,Marshal.ReadIntPtr(single));IntPtr classPool=Marshal.ReadIntPtr(pool,16);var mirror=Fn<Mirror>(lib,"boom_java_class_load");
            var mirrors=new List<IntPtr>();
            for(int i=0;i<arrayTypes.Length;i++){
                Reset(ctx);IntPtr m=mirror(ctx,classPool,arrayTypes[i]);Need(m!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Normal array Class mirror failed");mirrors.Add(m);
                Marshal.WriteIntPtr(argv,8,m);Reset(ctx);Need(native[1](ctx,argv)==0&&Marshal.ReadInt32(ctx)==0,"Normal array base differs");
                Reset(ctx);Need(native[2](ctx,argv)==expectedScales[i]&&Marshal.ReadInt32(ctx)==0,"Normal array scale differs");
            }
            Parallel.For(0,workers,w=>{
                IntPtr c=Marshal.AllocHGlobal(32),a=Marshal.AllocHGlobal(16);try{
                    Marshal.WriteIntPtr(a,Marshal.ReadIntPtr(single));
                    for(int i=0;i<iterations;i++){
                        int j=(i+w)%mirrors.Count;Marshal.WriteIntPtr(a,8,mirrors[j]);Reset(c);
                        Need(native[2](c,a)==expectedScales[j]&&Marshal.ReadInt32(c)==0,"Parallel array query differs");
                        Need(native[3](c,a)==0&&Marshal.ReadInt32(c)==0,"Parallel fullFence failed");
                    }
                }finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}
            });
            Marshal.WriteIntPtr(argv,8,IntPtr.Zero);Reset(ctx);Need(native[2](ctx,argv)==0&&Marshal.ReadInt32(ctx)==4,"Null Class accepted");errors++;
            Reset(ctx);IntPtr nonarray=mirror(ctx,classPool,unsafeId);Need(nonarray!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Normal non-array Class allocation failed");
            Marshal.WriteIntPtr(argv,8,nonarray);Reset(ctx);Need(native[1](ctx,argv)==0&&Marshal.ReadInt32(ctx)==7,"Non-array Class accepted");errors++;
            Marshal.WriteIntPtr(argv,IntPtr.Zero);Reset(ctx);Need(native[3](ctx,argv)==0&&Marshal.ReadInt32(ctx)==4,"Null Unsafe receiver accepted");errors++;
            Marshal.WriteIntPtr(argv,nonarray);Reset(ctx);Need(native[3](ctx,argv)==0&&Marshal.ReadInt32(ctx)==7,"Wrong normal receiver accepted");errors++;
            Reset(ctx);Marshal.WriteInt32(ctx,99);long before=Marshal.ReadInt64(heap,56);
            Need(kernel(ctx,argv,pool,0)==0&&fill(ctx,pool)==0&&Marshal.ReadInt32(ctx)==99&&Marshal.ReadInt32(ctx,4)==37&&Marshal.ReadInt32(ctx,8)==73&&Marshal.ReadInt64(heap,56)==before,"Pending Unsafe error overwritten");errors++;
            Need(kernel(IntPtr.Zero,argv,pool,0)==0&&fill(IntPtr.Zero,pool)==0,"Null native context accepted");errors++;
            IntPtr copy=Memory(memory,80);byte[] bytes=new byte[80];Marshal.Copy(pool,bytes,0,80);
            foreach(int offset in new[]{0,4,8,12,64,68}){
                Marshal.Copy(bytes,0,copy,80);Marshal.WriteInt32(copy,offset,1234567);Reset(ctx);
                Need(kernel(ctx,argv,copy,0)==0&&Marshal.ReadInt32(ctx)==7,"Invalid Unsafe pool accepted: "+offset);errors++;
            }
            foreach(int offset in new[]{16,24,32,40,48,56,72}){
                Marshal.Copy(bytes,0,copy,80);Marshal.WriteIntPtr(copy,offset,IntPtr.Zero);Reset(ctx);
                Need(kernel(ctx,argv,copy,0)==0&&Marshal.ReadInt32(ctx)==7,"Missing Unsafe metadata accepted: "+offset);errors++;
            }
            IntPtr bindingCopy=Memory(memory,72);byte[] bindings=new byte[72];Marshal.Copy(Marshal.ReadIntPtr(pool,48),bindings,0,72);
            foreach(int offset in new[]{0,4,8,16,20}){
                Marshal.Copy(bytes,0,copy,80);Marshal.WriteInt32(copy,8,0);Marshal.WriteIntPtr(copy,48,bindingCopy);Marshal.Copy(bindings,0,bindingCopy,72);
                if(offset==8)Marshal.WriteIntPtr(bindingCopy,offset,IntPtr.Zero);else Marshal.WriteInt32(bindingCopy,offset,-1);Reset(ctx);
                Need(kernel(ctx,argv,copy,0)==0&&Marshal.ReadInt32(ctx)==7&&Marshal.ReadInt32(copy,8)==0,"Invalid AOT native binding published: "+offset);errors++;
            }
            Reset(ctx);Need(native[0](ctx,argv)==0&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt32(pool,8)==2,"Repeated native registration differs");
            Need(Marshal.ReadInt32(NativeLibrary.GetExport(dll,"boom_diagnostic_pool"),8)==0,"Probe reached an unimplemented source dependency");
            return new long[]{workers,workers*iterations*2,arrayTypes.Length,staticNames.Length,errors,Marshal.ReadInt64(heap,56)};
        }finally{
            if(heap!=IntPtr.Zero)Need(destroy(heap)==1,"Unsafe heap cleanup failed");
            for(int i=memory.Count-1;i>=0;i--)Marshal.FreeHGlobal(memory[i]);if(dll!=IntPtr.Zero)NativeLibrary.Free(dll);NativeLibrary.Free(lib);
        }
    }
}
