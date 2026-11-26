// Controller only. Locale/BaseLocale are explicit preconstructor VM fixtures.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
public static class BoomLowercaseProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; public ulong Pending,Plan; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Entry(ref Context c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Service(ref Context c,[In] ulong[] a,IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Load(IntPtr h,IntPtr p,uint id,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Layout(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();
    static void Check(bool v,string why) { if(!v)throw new Exception(why); }
    static T Fn<T>(IntPtr m,string n) { IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p); }
    static ulong Bits(IntPtr p) { return unchecked((ulong)p.ToInt64()); }
    static IntPtr String(Alloc alloc,IntPtr heap,IntPtr strings,string units) {
        if(units=="null")return IntPtr.Zero;
        string[] words=units=="-"?new string[0]:units.Split(',');
        IntPtr chars=alloc(heap,(ulong)words.Length*2,0,261);Check(chars!=IntPtr.Zero,"Input chars allocation failed");
        for(int i=0;i<words.Length;i++)Marshal.WriteInt16(chars,i*2,unchecked((short)Convert.ToUInt16(words[i],16)));
        IntPtr value=alloc(heap,16,1,Bits(Marshal.ReadIntPtr(strings,40)));Check(value!=IntPtr.Zero,"VM String fixture allocation failed");Marshal.WriteIntPtr(value,chars);Marshal.WriteInt64(value,8,0);return value;
    }
    static string Text(IntPtr value,IntPtr strings) {
        Check(value!=IntPtr.Zero&&Marshal.ReadIntPtr(value,-8)==Marshal.ReadIntPtr(strings,40)&&Marshal.ReadInt64(value,-16)==16&&Marshal.ReadInt32(value,-20)==1,"Result String layout differs");
        IntPtr chars=Marshal.ReadIntPtr(value);Check(chars!=IntPtr.Zero&&Marshal.ReadInt64(chars,-8)==261,"Result backing is not UTF16");long bytes=Marshal.ReadInt64(chars,-16);Check(bytes>=0&&(bytes&1)==0&&bytes<=1048576,"Result String length invalid");
        var text=new StringBuilder();for(int i=0;i<bytes/2;i++)text.Append(unchecked((ushort)Marshal.ReadInt16(chars,i*2)).ToString("x4"));return text.ToString();
    }
    static IntPtr Storage(Alloc alloc,IntPtr heap,IntPtr tag) {
        int bytes=checked((int)Marshal.ReadInt64(tag,8));IntPtr value=alloc(heap,(ulong)bytes,(uint)Marshal.ReadInt32(tag,16),Bits(tag));Check(value!=IntPtr.Zero,"Locale storage allocation failed");Marshal.Copy(new byte[bytes],0,value,bytes);return value;
    }
    static IntPtr MakeLocale(Alloc alloc,IntPtr heap,IntPtr strings,IntPtr pool,IntPtr localeTag,IntPtr baseTag,Service intern,string language) {
        if(language=="null")return IntPtr.Zero;
        if(language=="-")language="";var units=new StringBuilder();foreach(char c in language){if(units.Length!=0)units.Append(',');units.Append(((int)c).ToString("x"));}
        IntPtr lang=String(alloc,heap,strings,units.Length==0?"-":units.ToString());var context=new Context();lang=intern(ref context,new[]{Bits(lang)},strings);Check(lang!=IntPtr.Zero&&context.Kind==0,"Language is not canonical/interned");
        IntPtr b=Storage(alloc,heap,baseTag);Marshal.WriteIntPtr(b,Marshal.ReadInt32(pool,60),lang);IntPtr locale=Storage(alloc,heap,localeTag);Marshal.WriteIntPtr(locale,Marshal.ReadInt32(pool,56),b);return locale;
    }
    static void GC(IntPtr m,IntPtr heap,params IntPtr[] extra) {
        IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n),all=Marshal.AllocHGlobal(checked(((int)n+extra.Length)*8));
        try {for(int i=0;i<n;i++)Marshal.WriteIntPtr(all,i*8,Marshal.ReadIntPtr(roots,i*8));for(int i=0;i<extra.Length;i++)Marshal.WriteIntPtr(all,((int)n+i)*8,extra[i]);Check(Fn<Collect>(m,"boom_heap_collect")(heap,all,n+(uint)extra.Length)!=ulong.MaxValue,"Lowercase root collection failed");}finally{Marshal.FreeHGlobal(all);}
    }
    public static void Packaged(string image,string runtime,int localeRow,int baseRow) {
        IntPtr m=LoadLibraryExW(image,IntPtr.Zero,0x1100),r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;Check(m!=IntPtr.Zero&&r!=IntPtr.Zero,"Packaged case image load failed");
        try {
            heap=Fn<Create>(r,"boom_heap_create")(65536);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Packaged case heap ABI differs");
            IntPtr pool=Fn<Pointer>(m,"boom_get_lowercase_pool")(),strings=Marshal.ReadIntPtr(pool,8),rows=Marshal.ReadIntPtr(Marshal.ReadIntPtr(pool,24),16);
            IntPtr localeTag=Marshal.ReadIntPtr(rows,localeRow*40),baseTag=Marshal.ReadIntPtr(rows,baseRow*40);var alloc=Fn<Alloc>(r,"boom_heap_alloc");var warm=new Context();Check(Fn<Load>(r,"boom_string_load")(heap,strings,0,ref warm)!=IntPtr.Zero&&warm.Kind==0,"Packaged case String pool failed");
            var query=Fn<Service>(r,"boom_string_lowercase");var intern=Fn<Service>(r,"boom_string_intern");
            string[] languages={"-","az","lt"},inputs={"27,301,130,3c3,49,ae5b,d800,dc00,3a3,307","49,307","49,301"},outputs={"002703010069030703c30069ae5bd800dc0003c30307","0069","006903070301"};
            for(int i=0;i<languages.Length;i++) {
                IntPtr source=String(alloc,heap,strings,inputs[i]),locale=MakeLocale(alloc,heap,strings,pool,localeTag,baseTag,intern,languages[i]);var c=new Context();IntPtr value=query(ref c,new[]{Bits(source),Bits(locale)},pool);
                Check(c.Kind==0&&Text(value,strings)==outputs[i],"Packaged context conversion differs at "+languages[i]);GC(m,heap,value);Check(Text(value,strings)==outputs[i],"Packaged case backing root lost");
            }
        } finally {if(heap!=IntPtr.Zero)Fn<One>(r,"boom_heap_destroy")(heap);if(r!=IntPtr.Zero)FreeLibrary(r);if(m!=IntPtr.Zero)FreeLibrary(m);}
    }
    public static string[] Run(string dll,string[] cases,int localeRow,int baseRow,uint npeClass,uint method) {
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),heap=IntPtr.Zero,foreign=IntPtr.Zero;Check(m!=IntPtr.Zero,"Lowercase image load failed");
        try {
            heap=Fn<Create>(m,"boom_heap_create")(8388608);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Lowercase heap bind failed");
            var alloc=Fn<Alloc>(m,"boom_heap_alloc");var entry=Fn<Entry>(m,"boom_entry32");var query=Fn<Service>(m,"boom_string_lowercase");
            IntPtr pool=Fn<Pointer>(m,"boom_get_lowercase_pool")(),strings=Marshal.ReadIntPtr(pool,8),rows=Marshal.ReadIntPtr(Marshal.ReadIntPtr(pool,24),16);
            IntPtr localeTag=Marshal.ReadIntPtr(rows,localeRow*40),baseTag=Marshal.ReadIntPtr(rows,baseRow*40);
            var warm=new Context();Check(Fn<Load>(m,"boom_string_load")(heap,strings,0,ref warm)!=IntPtr.Zero&&warm.Kind==0,"VM String literal initialization failed");
            var result=new List<string>();var internService=Fn<Service>(m,"boom_string_intern");
            foreach(string line in cases) {
                string[] fields=line.Split(' ');IntPtr source=String(alloc,heap,strings,fields[1]),locale=MakeLocale(alloc,heap,strings,pool,localeTag,baseTag,internService,fields[0]);
                var context=new Context();IntPtr lower=entry(ref context,new[]{Bits(source),Bits(locale)});Check(context.Depth==0,"Lowercase leaked Java frames");
                if(context.Kind==0) {
                    string text=Text(lower,strings);result.Add("v "+(lower==source?"1":"0")+" "+text);Check(source!=IntPtr.Zero,"Null String unexpectedly converted");
                    string original=fields[1]=="-"?"":string.Concat(Array.ConvertAll(fields[1].Split(','),v=>Convert.ToUInt16(v,16).ToString("x4")));
                    Check(Text(source,strings)==original,"Lowercase mutated source");GC(m,heap,lower);Check(Text(lower,strings)==text,"Lowercase backing root lost");
                } else {
                    Check(lower==IntPtr.Zero&&context.Kind==16&&context.Pending!=0&&context.Method==method&&context.PC==2,"Lowercase error lost source location: "+context.Kind+"/"+context.PC);
                    Check(Marshal.ReadIntPtr(new IntPtr(unchecked((long)context.Pending)),-8)==Fn<Layout>(m,"boom_get_object_layout")(npeClass),"Unexpected lowercase Throwable");result.Add("e java.lang.NullPointerException");
                }
                GC(m,heap);
            }
            var pending=new Context{Kind=23,PC=91,Method=37,Depth=2,Pending=0x1234,Plan=0x5678};Check(query(ref pending,null,IntPtr.Zero)==IntPtr.Zero&&pending.Kind==23&&pending.PC==91&&pending.Method==37&&pending.Depth==2&&pending.Pending==0x1234&&pending.Plan==0x5678,"Pending case context changed");
            // Foreign/wrong-type Locale storage is rejected before following fields.
            IntPtr simple=String(alloc,heap,strings,"41");foreign=Fn<Create>(m,"boom_heap_create")(4096);IntPtr badLocale=Storage(alloc,foreign,localeTag);var invalid=new Context();Check(query(ref invalid,new[]{Bits(simple),Bits(badLocale)},pool)==IntPtr.Zero&&invalid.Kind==7,"Foreign Locale accepted");
            invalid=new Context();Check(query(ref invalid,new[]{Bits(simple),Bits(simple)},pool)==IntPtr.Zero&&invalid.Kind==7,"String accepted as Locale");
            IntPtr foreignString=String(alloc,foreign,strings,"41");IntPtr rootLocale=MakeLocale(alloc,heap,strings,pool,localeTag,baseTag,internService,"-");invalid=new Context();Check(query(ref invalid,new[]{Bits(foreignString),Bits(rootLocale)},pool)==IntPtr.Zero&&invalid.Kind==7,"Foreign String accepted");
            IntPtr thai=MakeLocale(alloc,heap,strings,pool,localeTag,baseTag,internService,"th"),sigma=String(alloc,heap,strings,"41,3a3");invalid=new Context();Check(query(ref invalid,new[]{Bits(sigma),Bits(thai)},pool)==IntPtr.Zero&&invalid.Kind==20,"Unimplemented dictionary Sigma silently used root rules");
            IntPtr shared=String(alloc,heap,strings,"41,3a3,20,49,130,d83d,de00");var parallelValues=new IntPtr[2048];
            System.Threading.Tasks.Parallel.For(0,8,new System.Threading.Tasks.ParallelOptions{MaxDegreeOfParallelism=8},worker=> {
                for(int j=0;j<256;j++) {var parallel=new Context();IntPtr value=entry(ref parallel,new[]{Bits(shared),Bits(rootLocale)});Check(parallel.Kind==0&&parallel.Depth==0&&Text(value,strings)=="006103c20020006900690307d83dde00","Parallel contextual lower differs");parallelValues[worker*256+j]=value;}
            });
            Check(new HashSet<IntPtr>(parallelValues).Count==parallelValues.Length,"Lowercase allocated results share identity");
            IntPtr unchanged=String(alloc,heap,strings,"61"),needs=String(alloc,heap,strings,"41"),surrogate=String(alloc,heap,strings,"d800");
            while(alloc(heap,4096,0,267)!=IntPtr.Zero){}while(alloc(heap,0,0,267)!=IntPtr.Zero){}
            long full=Marshal.ReadInt64(heap,56);var oom=new Context();Check(query(ref oom,new[]{Bits(unchanged),Bits(rootLocale)},pool)==unchanged&&oom.Kind==0&&Marshal.ReadInt64(heap,56)==full,"Unchanged String allocated at full heap");
            oom=new Context();Check(query(ref oom,new[]{Bits(needs),Bits(rootLocale)},pool)==IntPtr.Zero&&oom.Kind==3&&Marshal.ReadInt64(heap,56)==full,"Changed String did not report OOM without collection");
            oom=new Context();Check(query(ref oom,new[]{Bits(surrogate),Bits(rootLocale)},pool)==IntPtr.Zero&&oom.Kind==3,"Surrogate String incorrectly skipped required copy");
            GC(m,heap,rootLocale,needs);var recovered=new Context();IntPtr again=query(ref recovered,new[]{Bits(needs),Bits(rootLocale)},pool);Check(recovered.Kind==0&&Text(again,strings)=="0061","Lowercase failed after explicit reclamation");GC(m,heap,again);Check(Text(again,strings)=="0061","Recovered backing was not rooted");
            return result.ToArray();
        } finally {Check(Fn<Release>(m,"boom_release_trace_pool")()==0,"Active lowercase frames at shutdown");if(foreign!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(foreign);if(heap!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(heap);FreeLibrary(m);}
    }
}
