// Disposable controller only. String allocation/construction and GC execute ASM.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class BoomStringConstructionProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; public ulong Pending,Plan; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Layout(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Entry(ref Context c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr New(ref Context c,IntPtr pool,IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void Construct(ref Context c,[In] ulong[] a,IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();
    static void Check(bool v,string why) { if(!v) throw new Exception(why); }
    static T Fn<T>(IntPtr m,string n) { IntPtr p=GetProcAddress(m,n); Check(p!=IntPtr.Zero,"Missing "+n); return Marshal.GetDelegateForFunctionPointer<T>(p); }
    static ulong Bits(IntPtr p) { return unchecked((ulong)p.ToInt64()); }
    static IntPtr Array(Alloc alloc,IntPtr heap,string units) {
        if(units=="null")return IntPtr.Zero;
        string[] words=units=="-"?new string[0]:units.Split(',');
        IntPtr a=alloc(heap,(ulong)words.Length*2,0,261); Check(a!=IntPtr.Zero,"Input char[] allocation failed");
        for(int i=0;i<words.Length;i++)Marshal.WriteInt16(a,i*2,unchecked((short)Convert.ToUInt16(words[i],16)));
        return a;
    }
    static string Text(IntPtr value,IntPtr pool) {
        Check(value!=IntPtr.Zero&&Marshal.ReadIntPtr(value,-8)==Marshal.ReadIntPtr(pool,40)&&Marshal.ReadInt64(value,-16)==16&&Marshal.ReadInt32(value,-20)==1,"String layout differs");
        IntPtr a=Marshal.ReadIntPtr(value); Check(a!=IntPtr.Zero&&Marshal.ReadInt64(a,-8)==261&&Marshal.ReadInt32(a,-20)==0,"String backing is not UTF16 char[]");
        long bytes=Marshal.ReadInt64(a,-16); Check(bytes>=0&&(bytes&1)==0&&bytes<=1048576,"String length invalid");
        var b=new StringBuilder("v "); for(int i=0;i<bytes/2;i++)b.Append(unchecked((ushort)Marshal.ReadInt16(a,i*2)).ToString("x4"));return b.ToString();
    }
    static void GC(IntPtr m,IntPtr heap,params IntPtr[] extra) {
        IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n),all=Marshal.AllocHGlobal(checked(((int)n+extra.Length)*8));
        try { for(int i=0;i<n;i++)Marshal.WriteIntPtr(all,i*8,Marshal.ReadIntPtr(roots,i*8));for(int i=0;i<extra.Length;i++)Marshal.WriteIntPtr(all,((int)n+i)*8,extra[i]);
            Check(Fn<Collect>(m,"boom_heap_collect")(heap,all,n+(uint)extra.Length)!=ulong.MaxValue,"Explicit collection failed");
        } finally { Marshal.FreeHGlobal(all); }
    }
    public static void Packaged(string image,string runtime) {
        IntPtr m=LoadLibraryExW(image,IntPtr.Zero,0x1100),r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;
        Check(m!=IntPtr.Zero&&r!=IntPtr.Zero,"Packaged runtime load failed");
        try {
            heap=Fn<Create>(r,"boom_heap_create")(65536);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Packaged heap ABI differs");
            IntPtr pool=Fn<Pointer>(m,"boom_get_constructor_string_pool")();Check(Marshal.ReadIntPtr(pool,48)==IntPtr.Zero,"Packaged cold test was prewarmed");
            var c=new Context();IntPtr value=Fn<New>(r,"boom_string_new")(ref c,pool,heap);Check(value!=IntPtr.Zero&&c.Kind==0,"Packaged cold String allocation failed");
            IntPtr source=Array(Fn<Alloc>(r,"boom_heap_alloc"),heap,"41,0,d83d,de00,d800,ffff");
            Fn<Construct>(r,"boom_string_construct_chars")(ref c,new[]{Bits(value),Bits(source),1UL,5UL},pool);
            Check(c.Kind==0&&Text(value,pool)=="v 0000d83dde00d800ffff","Packaged constructor ABI/UTF16 copy differs");GC(m,heap,value);
            Check(Text(value,pool)=="v 0000d83dde00d800ffff","Packaged String backing root lost");
            c=new Context();value=Fn<New>(r,"boom_string_new")(ref c,pool,heap);source=Array(Fn<Alloc>(r,"boom_heap_alloc"),heap,"41,0,d83d,de00,d800,ffff");Fn<Construct>(r,"boom_string_construct_chars_all")(ref c,new[]{Bits(value),Bits(source)},pool);Check(c.Kind==0&&Text(value,pool)=="v 00410000d83dde00d800ffff","Packaged full-array constructor differs");GC(m,heap,value);Check(Text(value,pool)=="v 00410000d83dde00d800ffff","Packaged full-array backing root lost");
        } finally {
            if(m!=IntPtr.Zero)Fn<Release>(m,"boom_release_trace_pool")();
            if(heap!=IntPtr.Zero)Fn<One>(r,"boom_heap_destroy")(heap);
            if(r!=IntPtr.Zero)FreeLibrary(r);if(m!=IntPtr.Zero)FreeLibrary(m);
        }
    }
    public static string[] ParsePath(string dll,string[] cases,uint npeClass) {
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),heap=IntPtr.Zero;
        Check(m!=IntPtr.Zero,"Original ParseUtil image load failed");
        try {
            heap=Fn<Create>(m,"boom_heap_create")(8388608);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Path heap bind failed");
            var alloc=Fn<Alloc>(m,"boom_heap_alloc");var entry=Fn<Entry>(m,"boom_entry32");var fresh=Fn<New>(m,"boom_string_new");var construct=Fn<Construct>(m,"boom_string_construct_chars");
            IntPtr pool=Fn<Pointer>(m,"boom_get_constructor_string_pool")();var result=new List<string>();
            foreach(string line in cases) {
                string[] f=line.Split(' ');IntPtr chars=Array(alloc,heap,f[0]),input=IntPtr.Zero;var c=new Context();
                if(chars!=IntPtr.Zero) {
                    input=fresh(ref c,pool,heap);Check(input!=IntPtr.Zero&&c.Kind==0,"Path input String allocation failed");
                    construct(ref c,new[]{Bits(input),Bits(chars),0UL,(ulong)Marshal.ReadInt64(chars,-16)/2},pool);Check(c.Kind==0,"Path input String construction failed");
                }
                c=new Context();IntPtr output=entry(ref c,new[]{Bits(input),(ulong)Convert.ToUInt32(f[1],16),(ulong)Convert.ToUInt32(f[2],16)});
                Check(c.Depth==0,"Original path code leaked frames");
                if(c.Kind==0) { string text=Text(output,pool);GC(m,heap,output);Check(Text(output,pool)==text,"Original path result lost after collection");result.Add(text); }
                else {
                    Check(output==IntPtr.Zero&&c.Kind==16&&c.Pending!=0&&Marshal.ReadIntPtr(new IntPtr(unchecked((long)c.Pending)),-8)==Fn<Layout>(m,"boom_get_object_layout")(npeClass),"Original path failed with unexpected exception: "+c.Kind+"/"+c.Method+"/"+c.PC);
                    result.Add("e java.lang.NullPointerException");
                }
                GC(m,heap);
            }
            return result.ToArray();
        } finally {
            Fn<Release>(m,"boom_release_trace_pool")();
            if(heap!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(heap);
            FreeLibrary(m);
        }
    }
    public static string[] Run(string dll,string[] cases,uint npeClass,uint boundsClass,uint method,uint constructorPC) {
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),heap=IntPtr.Zero,foreign=IntPtr.Zero;
        Check(m!=IntPtr.Zero,"String construction image load failed");
        try {
            var create=Fn<Create>(m,"boom_heap_create");heap=create(8388608);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"String heap bind failed");
            var alloc=Fn<Alloc>(m,"boom_heap_alloc");var entry=Fn<Entry>(m,"boom_entry32");var fresh=Fn<New>(m,"boom_string_new");var construct=Fn<Construct>(m,"boom_string_construct_chars");
            IntPtr pool=Fn<Pointer>(m,"boom_get_constructor_string_pool")();var output=new List<string>();
            Check(Marshal.ReadIntPtr(pool,48)==IntPtr.Zero,"Cold String pool was already bound");
            var coldValues=new IntPtr[8];
            System.Threading.Tasks.Parallel.For(0,8,worker=> {
                var cold=new Context();coldValues[worker]=fresh(ref cold,pool,heap);
                Check(coldValues[worker]!=IntPtr.Zero&&cold.Kind==0&&cold.Plan==0&&Marshal.ReadIntPtr(coldValues[worker])==IntPtr.Zero,"Cold String allocation depended on literal/exception preparation");
            });
            Check(new HashSet<IntPtr>(coldValues).Count==8&&Marshal.ReadIntPtr(pool,48)==heap,"Cold heap binding/identity race failed");GC(m,heap);
            foreach(string line in cases) {
                string[] f=line.Split(' ');IntPtr input=Array(alloc,heap,f[0]);uint offset=Convert.ToUInt32(f[1],16),count=Convert.ToUInt32(f[2],16);
                var c=new Context();IntPtr value=entry(ref c,new[]{Bits(input),(ulong)offset,(ulong)count});
                Check(c.Depth==0,"Construction left Java frames active");
                if(c.Kind==0) {
                    Check(c.Pending==0,"Successful constructor left pending exception");string text=Text(value,pool);output.Add(text);
                    IntPtr backing=Marshal.ReadIntPtr(value);Check(backing!=input,"Constructor aliases mutable input");
                    if(count!=0)Marshal.WriteInt16(input,checked((int)offset*2),unchecked((short)0x5555));
                    Check(Text(value,pool)==text,"Input mutation changed constructed String");GC(m,heap,value);
                    Check(Text(value,pool)==text,"Explicit rooting lost constructed String backing");
                } else {
                    Check(value==IntPtr.Zero&&c.Kind==16&&c.Pending!=0&&c.Method==method&&c.PC==constructorPC,"Constructor error lost type/source location: "+c.Kind+"/"+c.Method+"/"+c.PC);
                    IntPtr tag=Marshal.ReadIntPtr(new IntPtr(unchecked((long)c.Pending)),-8);
                    if(tag==Fn<Layout>(m,"boom_get_object_layout")(npeClass))output.Add("e java.lang.NullPointerException");
                    else if(tag==Fn<Layout>(m,"boom_get_object_layout")(boundsClass))output.Add("e java.lang.StringIndexOutOfBoundsException");
                    else throw new Exception("Unexpected construction Throwable type");
                }
                GC(m,heap);
            }
            var pending=new Context{Kind=23,PC=91,Method=37,Depth=2,Pending=0x1234,Plan=0x5678};
            Check(fresh(ref pending,IntPtr.Zero,IntPtr.Zero)==IntPtr.Zero,"Pending new String returned object");construct(ref pending,null,IntPtr.Zero);
            Check(pending.Kind==23&&pending.PC==91&&pending.Method==37&&pending.Depth==2&&pending.Pending==0x1234&&pending.Plan==0x5678,"Pending construction context changed");
            IntPtr shared=Array(alloc,heap,"0,41,4e2d,d83d,de00,d800,ffff");var values=new IntPtr[1024];
            System.Threading.Tasks.Parallel.For(0,8,new System.Threading.Tasks.ParallelOptions{MaxDegreeOfParallelism=8},worker=> {
                for(int i=0;i<128;i++) { var c=new Context();IntPtr value=entry(ref c,new[]{Bits(shared),0UL,7UL});
                    Check(c.Kind==0&&c.Depth==0&&Text(value,pool)=="v 000000414e2dd83dde00d800ffff","Parallel UTF16 constructor differs");values[worker*128+i]=value; }
            });
            Check(new HashSet<IntPtr>(values).Count==values.Length,"new String reused object identities");GC(m,heap);
            var raw=new Context();IntPtr receiver=fresh(ref raw,pool,heap);Check(receiver!=IntPtr.Zero&&raw.Kind==0,"Raw uninitialized String allocation failed");
            foreign=create(4096);IntPtr bad=Array(alloc,foreign,"41");raw=new Context();construct(ref raw,new[]{Bits(receiver),Bits(bad),0UL,1UL},pool);
            Check(raw.Kind==7&&Marshal.ReadIntPtr(receiver)==IntPtr.Zero,"Foreign input initialized receiver");
            raw=new Context();Check(fresh(ref raw,pool,foreign)==IntPtr.Zero&&raw.Kind==7&&Marshal.ReadIntPtr(pool,48)==heap,"String heap binding was replaced");
            bad=alloc(heap,2,0,264);raw=new Context();construct(ref raw,new[]{Bits(receiver),Bits(bad),0UL,1UL},pool);Check(raw.Kind==7,"Non-char[] input accepted");
            IntPtr source=Array(alloc,heap,"41,42");
            while(alloc(heap,4096,0,267)!=IntPtr.Zero){}while(alloc(heap,0,0,267)!=IntPtr.Zero){}
            long full=Marshal.ReadInt64(heap,56);raw=new Context();construct(ref raw,new[]{Bits(receiver),Bits(source),0UL,2UL},pool);
            Check(raw.Kind==3&&Marshal.ReadIntPtr(receiver)==IntPtr.Zero&&Marshal.ReadInt64(heap,56)==full,"Copy OOM published partial backing or collected automatically");
            raw=new Context();Check(fresh(ref raw,pool,heap)==IntPtr.Zero&&raw.Kind==3&&Marshal.ReadInt64(heap,56)==full,"String allocation OOM differs");
            GC(m,heap);source=Array(alloc,heap,"41,42");raw=new Context();IntPtr recovered=entry(ref raw,new[]{Bits(source),0UL,2UL});Check(raw.Kind==0&&Text(recovered,pool)=="v 00410042","Fresh construction failed after explicit OOM reclamation");
            return output.ToArray();
        } finally {
            Fn<Release>(m,"boom_release_trace_pool")();
            if(foreign!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(foreign);
            if(heap!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(heap);
            FreeLibrary(m);
        }
    }
}
