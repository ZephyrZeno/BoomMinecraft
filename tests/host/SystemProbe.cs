// Development driver; copying, allocation, type checks, workers and collection are MASM.
using System;
using System.Runtime.InteropServices;
public static class BoomSystemProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr r,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ArrayNew(IntPtr h,int n,uint kind,ref Context ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ObjectNew(IntPtr h,IntPtr layout,ref Context ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Copy(ref Context ctx,[In] ulong[] args,IntPtr map);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Dispatch(ref Context ctx,[In] ulong[] args,IntPtr pool,uint index);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ClassDescriptor(uint index);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr p,IntPtr fn,IntPtr input,IntPtr output,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr p);
    static void Check(bool ok,string text){if(!ok)throw new Exception(text);}
    static IntPtr Open(string p){IntPtr m=LoadLibraryExW(p,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"System DLL load failed");return m;}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static ulong Bits(IntPtr p){return unchecked((ulong)p.ToInt64());}
    static IntPtr Mem(int n){IntPtr p=Marshal.AllocHGlobal(n);for(int i=0;i<n;i++)Marshal.WriteByte(p,i,0);return p;}
    public static void Abi(string runtime){
        IntPtr module=Open(runtime),heap=IntPtr.Zero,map=Mem(32),rows=Mem(9*40),types=Mem(17*40),layout=Mem(24),pool=Mem(32),table=Mem(40);
        try{
            heap=Fn<Create>(module,"boom_heap_create")(65536);Check(heap!=IntPtr.Zero,"System ABI heap failed");
            Marshal.WriteInt32(map,0,0x52545950);Marshal.WriteInt32(map,4,1);Marshal.WriteInt32(map,8,9);Marshal.WriteInt32(map,12,17);Marshal.WriteIntPtr(map,16,rows);
            int[] shifts={0,1,2,3,0,1,2,3},flags={0,2,6,7,1,3,4,5};
            for(int i=0;i<17;i++){IntPtr t=IntPtr.Add(types,i*40);Marshal.WriteInt32(t,0,0x54595045);Marshal.WriteInt32(t,4,1);Marshal.WriteInt32(t,8,i<8?0:i<16?3:1);if(i<8)Marshal.WriteInt32(t,12,flags[i]);else if(i<16)Marshal.WriteIntPtr(t,16,IntPtr.Add(types,(i-8)*40));}
            for(int i=0;i<8;i++){IntPtr row=IntPtr.Add(rows,i*40);Marshal.WriteInt64(row,0,260+i);Marshal.WriteIntPtr(row,8,IntPtr.Add(types,(i+8)*40));Marshal.WriteInt32(row,16,i+8);Marshal.WriteInt32(row,20,1);Marshal.WriteInt32(row,36,shifts[i]);}
            Marshal.WriteInt32(layout,0,0x4f424a43);Marshal.WriteInt32(layout,4,1);Marshal.WriteInt64(layout,8,8);Marshal.WriteInt32(layout,20,1);
            Marshal.WriteIntPtr(rows,320,layout);Marshal.WriteIntPtr(rows,328,IntPtr.Add(types,640));Marshal.WriteInt32(rows,336,16);Marshal.WriteInt64(rows,344,8);
            var ctx=new Context();IntPtr obj=Fn<ObjectNew>(module,"boom_object_new")(heap,layout,ref ctx);Check(obj!=IntPtr.Zero&&ctx.Kind==0,"System ABI object allocation failed");
            var allocate=Fn<ArrayNew>(module,"boom_array_new");var copy=Fn<Copy>(module,"boom_system_arraycopy");var arrays=new IntPtr[8,2];
            for(int i=0;i<8;i++)for(int j=0;j<2;j++){ctx=new Context();arrays[i,j]=allocate(heap,16,(uint)(i+4),ref ctx);Check(arrays[i,j]!=IntPtr.Zero&&ctx.Kind==0,"System ABI array allocation failed");}
            int[,] ranges={{0,0,16},{0,2,14},{2,0,14},{3,3,10},{16,16,0},{0,15,1}};
            for(int kind=0;kind<8;kind++)for(int same=0;same<2;same++)for(int r=0;r<6;r++){
                int size=16<<shifts[kind];var source=new byte[size];var dest=new byte[size];for(int i=0;i<size;i++){source[i]=(byte)(i*131+17);dest[i]=(byte)(i*71+39);}
                if(kind==2){Array.Copy(BitConverter.GetBytes(0x7fa12345U),source,4);Array.Copy(BitConverter.GetBytes(0x80000000U),0,source,4,4);}
                if(kind==3){Array.Copy(BitConverter.GetBytes(0x7ff0000000000042UL),source,8);Array.Copy(BitConverter.GetBytes(0x8000000000000000UL),0,source,8,8);}
                IntPtr a=arrays[kind,0],b=arrays[kind,same==0?1:0];Marshal.Copy(source,0,a,size);if(same==0)Marshal.Copy(dest,0,b,size);else dest=(byte[])source.Clone();
                Array.Copy(source,ranges[r,0]<<shifts[kind],dest,ranges[r,1]<<shifts[kind],ranges[r,2]<<shifts[kind]);
                ctx=new Context();copy(ref ctx,new[]{Bits(a),(ulong)ranges[r,0],Bits(b),(ulong)ranges[r,1],(ulong)ranges[r,2]},map);Check(ctx.Kind==0,"System raw bit copy failed");
                byte[] actual=new byte[size];Marshal.Copy(b,actual,0,size);for(int i=0;i<size;i++)Check(actual[i]==dest[i],"System arraycopy changed raw floating/primitive bits or overlap result");
            }
            ulong src=Bits(arrays[0,0]),dst=Bits(arrays[0,1]),wrong=Bits(arrays[4,1]);
            ulong[][] bad={new ulong[]{0,0,dst,0,0},new ulong[]{src,0,0,0,0},new ulong[]{Bits(obj),0,0,0,0},new ulong[]{src,0,wrong,0,0},new ulong[]{src,0xffffffff,wrong,0,0},new ulong[]{Bits(obj),0,dst,0,0},new ulong[]{src,0xffffffff,dst,0,0},new ulong[]{src,0,dst,0x7fffffff,0},new ulong[]{src,16,dst,16,1},new ulong[]{src,0,dst,0,0xffffffff}};
            uint[] kinds={4,4,4,6,6,6,5,5,5,5};
            for(int i=0;i<bad.Length;i++){ctx=new Context();copy(ref ctx,bad[i],map);Check(ctx.Kind==kinds[i],"System null/type/bounds precedence mismatch");}
            Marshal.WriteInt32(map,4,255);ctx=new Context();copy(ref ctx,new[]{src,0UL,dst,0UL,0UL},map);Check(ctx.Kind==7,"System copy accepted invalid type map");Marshal.WriteInt32(map,4,1);
            Marshal.WriteInt32(pool,0,0x53595350);Marshal.WriteInt32(pool,4,1);Marshal.WriteIntPtr(pool,16,table);Marshal.WriteIntPtr(pool,24,map);
            Marshal.WriteInt32(table,0,0x5359534d);Marshal.WriteInt32(table,4,1);Marshal.WriteInt32(table,8,3);
            string[] targets={"boom_vm_current_time_millis","boom_vm_nano_time","boom_system_arraycopy"};for(int i=0;i<3;i++)Marshal.WriteIntPtr(table,16+i*8,GetProcAddress(module,targets[i]));
            var register=Fn<Copy>(module,"boom_system_register");var dispatch=Fn<Dispatch>(module,"boom_system_dispatch");
            ctx=new Context();dispatch(ref ctx,new ulong[0],pool,0);Check(ctx.Kind==20,"Unregistered native silently resolved");
            Marshal.WriteInt32(table,8,2);ctx=new Context();register(ref ctx,new ulong[0],pool);Check(ctx.Kind==7&&Marshal.ReadIntPtr(pool,8)==IntPtr.Zero,"Partial native table published");Marshal.WriteInt32(table,8,3);
            Marshal.WriteIntPtr(table,24,IntPtr.Zero);ctx=new Context();register(ref ctx,new ulong[0],pool);Check(ctx.Kind==7&&Marshal.ReadIntPtr(pool,8)==IntPtr.Zero,"Missing native implementation published");Marshal.WriteIntPtr(table,24,GetProcAddress(module,targets[1]));
            System.Threading.Tasks.Parallel.For(0,64,i=>{var local=new Context();register(ref local,new ulong[0],pool);Check(local.Kind==0,"Concurrent native registration failed");});
            Check(Marshal.ReadIntPtr(pool,8)==table,"Native registry did not publish its table");
            ctx=new Context();register(ref ctx,new ulong[0],pool);Check(ctx.Kind==0,"Idempotent native re-registration failed");
            ctx=new Context();Check(dispatch(ref ctx,new ulong[0],pool,0)>0&&ctx.Kind==0,"Registered millis dispatch failed");
            ctx=new Context();dispatch(ref ctx,new ulong[0],pool,1);Check(ctx.Kind==0,"Registered nanoTime dispatch failed");
            ctx=new Context();dispatch(ref ctx,new[]{src,0UL,dst,0UL,16UL},pool,2);Check(ctx.Kind==0,"Registered arraycopy dispatch failed");for(int i=0;i<16;i++)Check(Marshal.ReadByte(arrays[0,0],i)==Marshal.ReadByte(arrays[0,1],i),"Registered native copy did not execute");
            ctx=new Context();dispatch(ref ctx,new ulong[0],pool,3);Check(ctx.Kind==7,"Invalid registered native slot accepted");
            Marshal.WriteIntPtr(pool,8,IntPtr.Add(table,8));ctx=new Context();dispatch(ref ctx,new ulong[0],pool,0);Check(ctx.Kind==7,"Changed native publication accepted");
            Check(Marshal.ReadInt64(heap,56)==17,"System copy allocated guest objects");Check(Fn<Collect>(module,"boom_heap_collect")(heap,IntPtr.Zero,0)==17,"System ABI objects were not reclaimable");
        }finally{if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);foreach(IntPtr p in new[]{map,rows,types,layout,pool,table})Marshal.FreeHGlobal(p);FreeLibrary(module);}
    }
    public static void Parallel(string dll,string runtime,int systemClass){
        IntPtr module=Open(dll),library=Open(runtime),heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try{
            heap=Fn<Create>(module,"boom_heap_create")(4*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"System parallel heap failed");
            const int count=4099;var args=new long[count*16];for(int i=0;i<count;i++)args[i*16]=unchecked((uint)(0x80000000U+(uint)i*17));
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(args,0,input,args.Length);pool=Fn<PoolCreate>(library,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"System workers failed");
            for(int batch=0;batch<3;batch++){
                Check(Fn<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)==0,"System arraycopy parallel dispatch failed");
                for(int i=0;i<count;i++)Check(unchecked((uint)Marshal.ReadInt64(output,i*32))==unchecked((uint)(args[i*16]*11+35))&&Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0,"Concurrent System copy mismatch");
                if(systemClass>=0){IntPtr descriptor=Fn<ClassDescriptor>(module,"boom_get_class_descriptor")((uint)systemClass);Check(descriptor!=IntPtr.Zero&&Marshal.ReadInt32(descriptor,8)==2,"Original System clinit did not complete");}
                Check(Marshal.ReadInt64(heap,56)==count,"System copy allocated hidden temporary arrays");
                IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out uint n);Check(Fn<Collect>(module,"boom_heap_collect")(heap,roots,n)==count&&Marshal.ReadInt64(heap,56)==0,"System copy temporary arrays leaked");
            }
        }finally{if(pool!=IntPtr.Zero)Fn<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);FreeLibrary(library);FreeLibrary(module);}
    }
}
