// Disposable test controller; every guest split operation executes the ASM image.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class BoomSplitProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth;public ulong Pending,Plan; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Entry(ref Context c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Service(ref Context c,[In] ulong[] a,IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Intrinsic(ref Context c,[In] ulong[] a,IntPtr p,uint op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Load(IntPtr h,IntPtr p,uint id,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Layout(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();
    static void Check(bool v,string why){if(!v)throw new Exception(why);}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static ulong Bits(IntPtr p){return unchecked((ulong)p.ToInt64());}
    static IntPtr String(Alloc alloc,IntPtr heap,IntPtr strings,string units){
        if(units=="null")return IntPtr.Zero;string[] words=units=="-"?new string[0]:units.Split(',');
        IntPtr chars=alloc(heap,(ulong)words.Length*2,0,261);Check(chars!=IntPtr.Zero,"Fixture chars OOM");
        for(int i=0;i<words.Length;i++)Marshal.WriteInt16(chars,i*2,unchecked((short)Convert.ToUInt16(words[i],16)));
        IntPtr value=alloc(heap,16,1,Bits(Marshal.ReadIntPtr(strings,40)));Check(value!=IntPtr.Zero,"Fixture String OOM");Marshal.WriteIntPtr(value,chars);Marshal.WriteInt64(value,8,0);return value;
    }
    static string Text(IntPtr value,IntPtr strings){
        Check(value!=IntPtr.Zero&&Marshal.ReadIntPtr(value,-8)==Marshal.ReadIntPtr(strings,40)&&Marshal.ReadInt64(value,-16)==16&&Marshal.ReadInt32(value,-20)==1,"Invalid result String");
        IntPtr chars=Marshal.ReadIntPtr(value);Check(chars!=IntPtr.Zero&&Marshal.ReadInt64(chars,-8)==261,"Invalid result chars");long bytes=Marshal.ReadInt64(chars,-16);Check(bytes>=0&&(bytes&1)==0&&bytes<=1048576,"Invalid chars length");
        if(bytes==0)return "-";var b=new StringBuilder();for(int i=0;i<bytes/2;i++)b.Append(unchecked((ushort)Marshal.ReadInt16(chars,i*2)).ToString("x4"));return b.ToString();
    }
    static string ArrayText(IntPtr value,IntPtr source,IntPtr pool,int mode,IntPtr empty){
        IntPtr strings=Marshal.ReadIntPtr(pool,8);Check(value!=IntPtr.Zero&&Marshal.ReadIntPtr(value,-8)==Marshal.ReadIntPtr(pool,24),"Invalid String[] tag");
        int n=Marshal.ReadInt32(value,-20);Check(n>=0&&Marshal.ReadInt64(value,-16)==n*8L,"Invalid String[] refs/size");var b=new StringBuilder("v ").Append(n);IntPtr delimiter=IntPtr.Zero;
        for(int i=0;i<n;i++){IntPtr s=Marshal.ReadIntPtr(value,i*8);string text=Text(s,strings);b.Append(' ').Append(text).Append('@').Append(s==source?'1':'0');if(text=="-"&&s!=source)Check(s==empty,"Empty piece is not canonical");if(mode==2&&(i&1)==1){if(delimiter==IntPtr.Zero)delimiter=s;else Check(s==delimiter,"Delimiter identity was not reused");}}
        return b.ToString();
    }
    static void GC(IntPtr m,IntPtr heap,params IntPtr[] extra){
        IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n),all=Marshal.AllocHGlobal(checked(((int)n+extra.Length)*8));
        try{for(int i=0;i<n;i++)Marshal.WriteIntPtr(all,i*8,Marshal.ReadIntPtr(roots,i*8));for(int i=0;i<extra.Length;i++)Marshal.WriteIntPtr(all,((int)n+i)*8,extra[i]);Check(Fn<Collect>(m,"boom_heap_collect")(heap,all,n+(uint)extra.Length)!=ulong.MaxValue,"Split collection failed");}finally{Marshal.FreeHGlobal(all);}
    }
    public static void Packaged(string image,string runtime){
        IntPtr m=LoadLibraryExW(image,IntPtr.Zero,0x1100),r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;Check(m!=IntPtr.Zero&&r!=IntPtr.Zero,"Packaged split DLL load failed");
        try{
            heap=Fn<Create>(r,"boom_heap_create")(65536);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Packaged split heap bind failed");var alloc=Fn<Alloc>(r,"boom_heap_alloc");IntPtr pool=Fn<Pointer>(m,"boom_get_split_pool")(),strings=Marshal.ReadIntPtr(pool,8);var c=new Context();IntPtr empty=Fn<Load>(r,"boom_string_load")(heap,strings,unchecked((uint)Marshal.ReadInt32(pool,32)),ref c);Check(c.Kind==0&&Text(empty,strings)=="-","Packaged empty literal differs");
            IntPtr source=String(alloc,heap,strings,"7c,61,7c,7c,62,7c"),regex=String(alloc,heap,strings,"5c,7c");var query=Fn<Service>(r,"boom_string_split");
            c=new Context();IntPtr value=query(ref c,new[]{Bits(source),Bits(regex),0UL,1UL},pool);string expected="v 8 -@0 007c@0 0061@0 007c@0 -@0 007c@0 0062@0 007c@0";
            Check(c.Kind==0&&ArrayText(value,source,pool,2,empty)==expected,"Packaged delimiter split differs");GC(m,heap,value);Check(ArrayText(value,source,pool,2,empty)==expected,"Packaged split roots lost");
            IntPtr trim=String(alloc,heap,strings,"20,0,4e2d,d800,20"),unchanged=String(alloc,heap,strings,"4e2d");var intrinsic=Fn<Intrinsic>(r,"boom_string_intrinsic");c=new Context();IntPtr trimmed=intrinsic(ref c,new[]{Bits(trim)},strings,19);Check(c.Kind==0&&Text(trimmed,strings)=="4e2dd800","Packaged trim differs");GC(m,heap,trimmed,unchanged);Check(Text(trimmed,strings)=="4e2dd800","Packaged trim roots lost");
            while(alloc(heap,4096,0,267)!=IntPtr.Zero){}while(alloc(heap,0,0,267)!=IntPtr.Zero){}long full=Marshal.ReadInt64(heap,56);c=new Context();Check(intrinsic(ref c,new[]{Bits(unchanged)},strings,19)==unchanged&&c.Kind==0&&Marshal.ReadInt64(heap,56)==full,"Unchanged trim allocates at full heap");
        }finally{if(heap!=IntPtr.Zero)Fn<One>(r,"boom_heap_destroy")(heap);if(r!=IntPtr.Zero)FreeLibrary(r);if(m!=IntPtr.Zero)FreeLibrary(m);}
    }
    public static string[] Run(string dll,string[] cases,uint npeClass){
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),heap=IntPtr.Zero,foreign=IntPtr.Zero;Check(m!=IntPtr.Zero,"Split DLL load failed");
        try{
            heap=Fn<Create>(m,"boom_heap_create")(8388608);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Split heap bind failed");
            var alloc=Fn<Alloc>(m,"boom_heap_alloc");var entry=Fn<Entry>(m,"boom_entry32");var query=Fn<Service>(m,"boom_string_split");IntPtr pool=Fn<Pointer>(m,"boom_get_split_pool")(),strings=Marshal.ReadIntPtr(pool,8);
            var c=new Context();IntPtr empty=Fn<Load>(m,"boom_string_load")(heap,strings,unchecked((uint)Marshal.ReadInt32(pool,32)),ref c);Check(c.Kind==0&&Text(empty,strings)=="-","Split empty literal missing");var results=new List<string>();
            foreach(string line in cases){string[] f=line.Split(' ');int mode=int.Parse(f[0]),limit=int.Parse(f[1]);IntPtr source=String(alloc,heap,strings,f[2]),regex=String(alloc,heap,strings,f[3]);string before=source==IntPtr.Zero?null:Text(source,strings);c=new Context();
                IntPtr value=entry(ref c,new[]{Bits(source),Bits(regex),unchecked((ulong)(long)limit),(ulong)mode});Check(c.Depth==0,"Split Java frame leaked");
                if(c.Kind==0){string text=ArrayText(value,source,pool,mode,empty);results.Add(text);Check(Text(source,strings)==before,"Split changed source");GC(m,heap,value);Check(ArrayText(value,source,pool,mode,empty)==text,"Result elements/backings lost after GC");}
                else{Check(value==IntPtr.Zero&&c.Kind==16&&c.Pending!=0,"Split exception not materialized: "+c.Kind);Check(Marshal.ReadIntPtr(new IntPtr(unchecked((long)c.Pending)),-8)==Fn<Layout>(m,"boom_get_object_layout")(npeClass),"Split exception class differs");results.Add("e java.lang.NullPointerException");}
                GC(m,heap);
            }
            var pending=new Context{Kind=23,PC=91,Method=37,Depth=2,Pending=0x1234,Plan=0x5678};Check(query(ref pending,null,IntPtr.Zero)==IntPtr.Zero&&pending.Kind==23&&pending.PC==91&&pending.Method==37&&pending.Depth==2&&pending.Pending==0x1234&&pending.Plan==0x5678,"Pending split context changed");
            IntPtr shared=String(alloc,heap,strings,"61,7c,62,7c,63"),pipe=String(alloc,heap,strings,"5c,7c");
            foreach(string regexText in new[]{"-","2e","5c,64","61,62","d800","5c,d800","5b,61,5d"}){IntPtr regex=String(alloc,heap,strings,regexText);c=new Context();Check(query(ref c,new[]{Bits(shared),Bits(regex),0UL,0UL},pool)==IntPtr.Zero&&c.Kind==20,"Unsupported regex silently treated as literal");}
            foreign=Fn<Create>(m,"boom_heap_create")(4096);IntPtr foreignString=String(alloc,foreign,strings,"61");c=new Context();Check(query(ref c,new[]{Bits(foreignString),Bits(pipe),0UL,0UL},pool)==IntPtr.Zero&&c.Kind==7,"Foreign split String accepted");
            IntPtr wrong=alloc(heap,16,0,267);c=new Context();Check(query(ref c,new[]{Bits(wrong),Bits(pipe),0UL,0UL},pool)==IntPtr.Zero&&c.Kind==7,"Non-String accepted by split");
            IntPtr badPool=Marshal.AllocHGlobal(48);try{byte[] bytes=new byte[48];Marshal.Copy(pool,bytes,0,48);Marshal.Copy(bytes,0,badPool,48);Marshal.WriteInt32(badPool,36,1);c=new Context();Check(query(ref c,new[]{Bits(shared),Bits(pipe),0UL,0UL},badPool)==IntPtr.Zero&&c.Kind==7,"Invalid split flags accepted");Marshal.Copy(bytes,0,badPool,48);Marshal.WriteInt32(badPool,32,int.MaxValue);c=new Context();Check(query(ref c,new[]{Bits(shared),Bits(pipe),0UL,0UL},badPool)==IntPtr.Zero&&c.Kind==7,"Invalid split empty index accepted");}finally{Marshal.FreeHGlobal(badPool);}
            var values=new IntPtr[2048];System.Threading.Tasks.Parallel.For(0,8,new System.Threading.Tasks.ParallelOptions{MaxDegreeOfParallelism=8},worker=>{for(int j=0;j<256;j++){var parallel=new Context();IntPtr value=entry(ref parallel,new[]{Bits(shared),Bits(pipe),0UL,2UL});Check(parallel.Kind==0&&parallel.Depth==0&&ArrayText(value,shared,pool,2,empty)=="v 5 0061@0 007c@0 0062@0 007c@0 0063@0","Parallel split differs");values[worker*256+j]=value;}});Check(new HashSet<IntPtr>(values).Count==values.Length,"Parallel split arrays share identity");
            while(alloc(heap,4096,0,267)!=IntPtr.Zero){}while(alloc(heap,0,0,267)!=IntPtr.Zero){}long full=Marshal.ReadInt64(heap,56);c=new Context();Check(query(ref c,new[]{Bits(shared),Bits(pipe),0UL,0UL},pool)==IntPtr.Zero&&c.Kind==3&&Marshal.ReadInt64(heap,56)==full,"Split OOM silently collected/allocated");
            GC(m,heap,shared,pipe);c=new Context();IntPtr recovered=query(ref c,new[]{Bits(shared),Bits(pipe),0UL,0UL},pool);Check(c.Kind==0&&ArrayText(recovered,shared,pool,1,empty)=="v 3 0061@0 0062@0 0063@0","Split failed after explicit reclamation");
            return results.ToArray();
        }finally{Check(Fn<Release>(m,"boom_release_trace_pool")()==0,"Active split frames at shutdown");if(foreign!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(foreign);if(heap!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(heap);FreeLibrary(m);}
    }
}
