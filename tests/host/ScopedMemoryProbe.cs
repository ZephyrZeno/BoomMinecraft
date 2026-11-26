// Controller only. Original Java bootstrap/getter and native registration are MASM.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomScopedMemoryProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context{public uint Kind,PC,Method,Depth;public ulong Pending,Plan;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Layout(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Entry(ref Context c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void Register(ref Context c,IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Unavailable(ref Context c,[In] ulong[] a,IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Static(uint owner,uint field);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Close();
    static void Check(bool v,string why){if(!v)throw new Exception(why);}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    public static void Run(string dll,uint owner,uint unsafeField,uint singletonField){
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),heap=IntPtr.Zero,copy=IntPtr.Zero;Check(m!=IntPtr.Zero,"Scoped memory image load failed");
        try{
            heap=Fn<Create>(m,"boom_heap_create")(4194304);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Scoped heap bind failed");
            IntPtr pool=Fn<Pointer>(m,"boom_get_scoped_native_pool")();var register=Fn<Register>(m,"boom_scoped_native_register");var entry=Fn<Entry>(m,"boom_entry32");
            Check(Marshal.ReadInt32(pool,8)==0,"Registration was published before Java initialization");
            var pending=new Context{Kind=23,PC=91,Method=37,Depth=2,Pending=0x1234,Plan=0x5678};register(ref pending,pool);
            Check(pending.Kind==23&&pending.PC==91&&pending.Method==37&&pending.Depth==2&&pending.Pending==0x1234&&pending.Plan==0x5678&&Marshal.ReadInt32(pool,8)==0,"Pending registration context/publication changed");
            copy=Marshal.AllocHGlobal(32);var bytes=new byte[32];Marshal.Copy(pool,bytes,0,32);Marshal.Copy(bytes,0,copy,32);Marshal.WriteIntPtr(copy,16,IntPtr.Zero);var invalid=new Context();register(ref invalid,copy);Check(invalid.Kind==7&&Marshal.ReadInt32(copy,8)==0,"Malformed scoped registration target accepted");
            var values=new IntPtr[4096];System.Threading.Tasks.Parallel.For(0,8,new System.Threading.Tasks.ParallelOptions{MaxDegreeOfParallelism=8},worker=>{
                for(int i=0;i<512;i++){var c=new Context();IntPtr value=entry(ref c,Array.Empty<ulong>());Check(value!=IntPtr.Zero&&c.Kind==0&&c.Depth==0&&c.Pending==0,"Original ScopedMemoryAccess bootstrap/getter failed: "+c.Kind);values[worker*512+i]=value;}
            });
            IntPtr first=values[0];foreach(IntPtr value in values)Check(value==first,"Concurrent singleton identity differs");
            Check(Marshal.ReadInt32(pool,8)==2&&Marshal.ReadInt32(pool,12)==1&&Marshal.ReadIntPtr(pool,16)==GetProcAddress(m,"boom_scoped_close_unavailable"),"Scoped native table differs");
            IntPtr layout=Fn<Layout>(m,"boom_get_object_layout")(owner);Check(layout!=IntPtr.Zero&&Marshal.ReadIntPtr(first,-8)==layout&&Marshal.ReadInt64(first,-16)==Marshal.ReadInt64(layout,8),"Singleton has the wrong runtime layout");
            var field=Fn<Static>(m,"boom_get_static_field");Check(Marshal.ReadIntPtr(field(owner,singletonField))==first&&Marshal.ReadIntPtr(field(owner,unsafeField))!=IntPtr.Zero,"Original final static fields were not published");
            ulong before=(ulong)Marshal.ReadInt64(heap,56);for(int i=0;i<256;i++){var c=new Context();register(ref c,pool);Check(c.Kind==0,"Idempotent native registration failed");}Check((ulong)Marshal.ReadInt64(heap,56)==before,"Native registration allocated guest objects");
            var unavailable=new Context();Check(Fn<Unavailable>(m,"boom_scoped_close_unavailable")(ref unavailable,Array.Empty<ulong>(),pool)==IntPtr.Zero&&unavailable.Kind==20,"Unimplemented close handshake reported success");
            IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint count);var seen=new HashSet<IntPtr>();var todo=new Stack<IntPtr>();for(int i=0;i<count;i++)todo.Push(Marshal.ReadIntPtr(roots,i*8));while(todo.Count>0){IntPtr obj=todo.Pop();if(obj==IntPtr.Zero||!seen.Add(obj))continue;uint refs=(uint)Marshal.ReadInt32(obj,-20);for(uint i=0;i<refs;i++)todo.Push(Marshal.ReadIntPtr(obj,checked((int)i*8)));}
            Check(seen.Contains(first)&&seen.Contains(Marshal.ReadIntPtr(field(owner,unsafeField))),"Scoped singleton/Unsafe are not strong roots");
            Check(Fn<Collect>(m,"boom_heap_collect")(heap,roots,count)!=ulong.MaxValue&&(ulong)Marshal.ReadInt64(heap,56)==(ulong)seen.Count,"Scoped bootstrap root collection differs");var after=new Context();Check(entry(ref after,Array.Empty<ulong>())==first&&after.Kind==0,"Scoped singleton changed after collection");
        }finally{if(m!=IntPtr.Zero){Fn<Close>(m,"boom_release_trace_pool")();if(heap!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(heap);if(copy!=IntPtr.Zero)Marshal.FreeHGlobal(copy);FreeLibrary(m);}}
    }
}
