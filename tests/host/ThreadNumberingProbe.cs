// Executes the original locked Thread$ThreadNumbering Java initializer and next.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
public static class BoomThreadNumberingProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context{public uint Kind,PC,Method,Depth;public ulong Pending,Plan;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)]static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")]static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int One(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Entry(ref Context c,IntPtr a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Field(uint c,uint slot);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Collect(IntPtr h,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate uint Release();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Indexed(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Pointer();
    static void Check(bool b,string s){if(!b)throw new Exception(s);}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    public static void Run(string dll,string runtime,uint owner,uint nextSlot){
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;
        Check(m!=IntPtr.Zero&&r!=IntPtr.Zero,"Thread numbering images");
        try{
            heap=Fn<Create>(r,"boom_heap_create")(16777216);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Thread numbering heap");
            var entry=Fn<Entry>(m,"boom_entry32");var results=new int[8192];
            Parallel.For(0,8,worker=>{for(int i=0;i<1024;i++){var c=new Context();int value=unchecked((int)entry(ref c,IntPtr.Zero));Check(c.Kind==0&&c.Depth==0,"Original thread numbering failed: "+c.Kind+" method="+c.Method+" pc="+c.PC);results[worker*1024+i]=value;}});
            var seen=new HashSet<int>(results);Check(seen.Count==8192,"Thread numbers duplicated");for(int i=0;i<8192;i++)Check(seen.Contains(i),"Thread number sequence has holes");
            IntPtr counter=Fn<Field>(m,"boom_get_static_field")(owner,nextSlot);Check(counter!=IntPtr.Zero&&Marshal.ReadInt32(counter)==8192,"Original next static cell was not updated");
            long live=Marshal.ReadInt64(heap,56),span=Marshal.ReadInt64(heap,48);
            for(int i=0;i<256;i++){var c=new Context();Check(unchecked((int)entry(ref c,IntPtr.Zero))==8192+i&&c.Kind==0,"Warm thread numbering differs");}
            Check(Marshal.ReadInt64(heap,56)==live&&Marshal.ReadInt64(heap,48)==span,"Hot counter allocated Java objects");
            Marshal.WriteInt32(counter,int.MaxValue-2);int[] wrap={int.MaxValue-2,int.MaxValue-1,int.MaxValue,int.MinValue,int.MinValue+1};
            foreach(int expected in wrap){var c=new Context();Check(unchecked((int)entry(ref c,IntPtr.Zero))==expected&&c.Kind==0,"Java int overflow differs");}
            Check(Marshal.ReadInt64(Fn<Pointer>(m,"boom_get_trace_pool")(),32)==0,"Thread numbering frames remained active");
            IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n);Check(Fn<Collect>(r,"boom_heap_collect")(heap,roots,n)!=ulong.MaxValue,"Counter quiescent collection failed");
            int beforeAfter=Marshal.ReadInt32(counter);var after=new Context();int actualAfter=unchecked((int)entry(ref after,IntPtr.Zero));int pendingClass=-1;if(after.Pending!=0){IntPtr tag=Marshal.ReadIntPtr(new IntPtr(unchecked((long)after.Pending)),-8);var layouts=Fn<Indexed>(m,"boom_get_object_layout");for(uint i=0;i<512;i++)if(layouts(i)==tag)pendingClass=(int)i;}
            Check(actualAfter==int.MinValue+2&&after.Kind==0,"Static counter did not survive collection: before="+beforeAfter+" actual="+actualAfter+" kind="+after.Kind+" class="+pendingClass+" method="+after.Method+" pc="+after.PC);
        }finally{if(m!=IntPtr.Zero&&GetProcAddress(m,"boom_release_trace_pool")!=IntPtr.Zero)Fn<Release>(m,"boom_release_trace_pool")();if(heap!=IntPtr.Zero)Fn<One>(r,"boom_heap_destroy")(heap);if(r!=IntPtr.Zero)FreeLibrary(r);if(m!=IntPtr.Zero)FreeLibrary(m);}
    }
}
