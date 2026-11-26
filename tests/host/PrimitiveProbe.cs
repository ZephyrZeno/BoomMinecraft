// Development-only P/Invoke driver. Primitive lookup, mirrors, collection and workers are MASM.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomPrimitiveProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string path,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr pool,IntPtr entry,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Load(IntPtr heap,IntPtr pool,uint index,ref Context ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Lookup(ref Context ctx,[In] ulong[] args,IntPtr pool,IntPtr ids);
    static T Fn<T>(IntPtr module,string name){IntPtr p=GetProcAddress(module,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static IntPtr Open(string path){IntPtr p=LoadLibraryExW(path,IntPtr.Zero,0x1100);Check(p!=IntPtr.Zero,"DLL open failed");return p;}
    static void Check(bool good,string message){if(!good)throw new Exception(message);}
    public static void Parallel(string dll,string runtime){
        IntPtr module=Open(dll),library=Open(runtime),heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try{
            heap=Fn<Create>(module,"boom_heap_create")(4*1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Primitive heap failed");
            const int count=3075;long[] values=new long[count*16];for(int i=0;i<count;i++)values[i*16]=i;
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(values,0,input,values.Length);
            pool=Fn<PoolCreate>(library,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Primitive worker pool failed");long retained=-1;
            for(int batch=0;batch<3;batch++){
                Check(Fn<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)==0,"Primitive parallel dispatch failed");
                for(int i=0;i<count;i++)Check(Marshal.ReadInt64(output,i*32)==485&&Marshal.ReadInt64(output,i*32+8)==0&&Marshal.ReadInt64(output,i*32+16)==0&&Marshal.ReadInt64(output,i*32+24)==0,"Concurrent wrapper/mirror identity mismatch");
                IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out uint rootCount);Check(Fn<Collect>(module,"boom_heap_collect")(heap,roots,rootCount)!=ulong.MaxValue,"Primitive quiescent collection failed");
                long live=Marshal.ReadInt64(heap,56);Check(live>0&&(retained<0||retained==live),"Primitive roots grew or disappeared");retained=live;
            }
        }finally{if(pool!=IntPtr.Zero)Fn<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);FreeLibrary(library);FreeLibrary(module);}
    }
    public static void Abi(string runtime){
        IntPtr library=Open(runtime),heap=IntPtr.Zero;var owned=new List<IntPtr>();
        Func<int,IntPtr> mem=n=>{IntPtr p=Marshal.AllocHGlobal(n);for(int i=0;i<n;i++)Marshal.WriteByte(p,i,0);owned.Add(p);return p;};
        string[] names={"boolean","byte","char","short","int","long","float","double","void","","Int","[I","int\0","voidx","java.lang.Integer","\ud800","😀"};
        try{
            heap=Fn<Create>(library,"boom_heap_create")(65536);Check(heap!=IntPtr.Zero,"Primitive ABI heap failed");
            IntPtr pool=mem(64),strings=mem(56),roots=mem((names.Length+9)*8),rows=mem(9*24),types=mem(9*40),ids=mem(9*4),mirrorLayout=mem(24),stringLayout=mem(24),entries=mem(names.Length*16);
            foreach(IntPtr layout in new[]{mirrorLayout,stringLayout}){Marshal.WriteInt32(layout,0,0x4f424a43);Marshal.WriteInt32(layout,4,1);}
            Marshal.WriteInt64(mirrorLayout,8,8);Marshal.WriteInt32(mirrorLayout,20,1);
            Marshal.WriteInt64(stringLayout,8,16);Marshal.WriteInt32(stringLayout,16,1);Marshal.WriteInt32(stringLayout,20,2);
            Marshal.WriteInt32(pool,0,0x4d495252);Marshal.WriteInt32(pool,4,1);Marshal.WriteInt32(pool,12,9);Marshal.WriteIntPtr(pool,16,roots);Marshal.WriteIntPtr(pool,24,rows);Marshal.WriteIntPtr(pool,32,mirrorLayout);Marshal.WriteIntPtr(pool,40,strings);
            Marshal.WriteInt32(strings,0,0x53545250);Marshal.WriteInt32(strings,4,2);Marshal.WriteInt32(strings,16,names.Length);Marshal.WriteIntPtr(strings,24,IntPtr.Add(roots,72));Marshal.WriteIntPtr(strings,32,entries);Marshal.WriteIntPtr(strings,40,stringLayout);
            for(int i=0;i<9;i++){IntPtr t=IntPtr.Add(types,i*40);Marshal.WriteInt32(t,0,0x54595045);Marshal.WriteInt32(t,4,1);Marshal.WriteInt32(t,12,i);Marshal.WriteIntPtr(rows,i*24,t);Marshal.WriteInt32(rows,i*24+12,-1);Marshal.WriteInt32(rows,i*24+16,-1);Marshal.WriteInt32(ids,i*4,i);}
            for(int i=0;i<names.Length;i++){IntPtr text=mem((names[i].Length+1)*2);for(int j=0;j<names[i].Length;j++)Marshal.WriteInt16(text,j*2,unchecked((short)names[i][j]));Marshal.WriteIntPtr(entries,i*16,text);Marshal.WriteInt32(entries,i*16+8,names[i].Length);}
            var load=Fn<Load>(library,"boom_string_load");var mirror=Fn<Load>(library,"boom_mirror_load");var lookup=Fn<Lookup>(library,"boom_mirror_primitive");var values=new ulong[names.Length];
            for(int i=0;i<names.Length;i++){
                var ctx=new Context();IntPtr value=load(heap,strings,(uint)i,ref ctx);Check(value!=IntPtr.Zero&&ctx.Kind==0,"Primitive name allocation failed");values[i]=unchecked((ulong)value.ToInt64());
                IntPtr result=lookup(ref ctx,new[]{values[i]},pool,ids);
                if(i<9){Check(result!=IntPtr.Zero&&ctx.Kind==0&&Marshal.ReadInt64(result)==i,"Primitive exact lookup failed");Check(mirror(heap,pool,(uint)i,ref ctx)==result&&ctx.Kind==0,"Primitive lookup created a distinct mirror");}
                else Check(result==IntPtr.Zero&&ctx.Kind==19,"Unknown primitive name did not retain ClassNotFoundException");
            }
            var error=new Context();lookup(ref error,new ulong[]{0},pool,ids);Check(error.Kind==4,"Primitive null name did not retain NPE");
            Marshal.WriteInt32(ids,16,0);error=new Context();lookup(ref error,new[]{values[4]},pool,ids);Check(error.Kind==7,"Mismatched primitive id kind accepted");Marshal.WriteInt32(ids,16,4);
            error=new Context();lookup(ref error,new[]{unchecked((ulong)Marshal.ReadIntPtr(roots).ToInt64())},pool,ids);Check(error.Kind==7,"Primitive non-String name accepted");
            Marshal.WriteInt32(pool,4,255);error=new Context();lookup(ref error,new[]{values[4]},pool,ids);Check(error.Kind==7,"Primitive invalid mirror ABI accepted");Marshal.WriteInt32(pool,4,1);
            Check(Fn<Collect>(library,"boom_heap_collect")(heap,roots,(uint)(names.Length+9))==0,"Primitive rooted identities were reclaimed");
            for(int i=0;i<9;i++){var ctx=new Context();IntPtr result=lookup(ref ctx,new[]{values[i]},pool,ids);Check(ctx.Kind==0&&result==Marshal.ReadIntPtr(roots,i*8),"Primitive mirror changed after collection");}
        }finally{if(heap!=IntPtr.Zero)Fn<Destroy>(library,"boom_heap_destroy")(heap);for(int i=owned.Count-1;i>=0;i--)Marshal.FreeHGlobal(owned[i]);FreeLibrary(library);}
    }
}
