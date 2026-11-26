// Test controller and explicit VM object fixtures; game execution stays in ASM.
using System;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
public static class BoomClassValueFieldProbe {
    [StructLayout(LayoutKind.Sequential)]struct Context { public uint Kind,PC,Method,Depth;public ulong Pending,Plan; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)]static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")]static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Indexed(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Alloc(IntPtr heap,ulong bytes,uint refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Mirror(IntPtr heap,IntPtr pool,uint id,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Entry(ref Context c,[In]ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Field(ref Context c,[In]ulong[] args,IntPtr pool,uint write);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Roots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate uint Release();
    static void Check(bool v,string why){if(!v)throw new Exception(why);}
    static T Fn<T>(IntPtr module,string name){IntPtr p=GetProcAddress(module,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static ulong Bits(IntPtr p){return unchecked((ulong)p.ToInt64());}
    public static string[] Run(string dll,string runtime,uint[] ids,uint mapClass,ulong bytes,uint refs,uint cacheOffset,uint npeClass,uint entryId){
        IntPtr image=LoadLibraryExW(dll,IntPtr.Zero,0x1100),rt=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero,foreign=IntPtr.Zero;
        Check(image!=IntPtr.Zero&&rt!=IntPtr.Zero,"ClassValue images failed to load");
        try {
            heap=Fn<Create>(rt,"boom_heap_create")(33554432);Check(heap!=IntPtr.Zero&&Fn<One>(image,"boom_bind_heap")(heap)==1,"ClassValue heap bind failed");
            IntPtr pool=Fn<Pointer>(image,"boom_get_class_value_pool")(),mirrors=Marshal.ReadIntPtr(pool,16),tag=Fn<Indexed>(image,"boom_get_object_layout")(mapClass);Check(tag!=IntPtr.Zero&&cacheOffset+8<=refs*8,"ClassValue cache field outside GC prefix");
            var alloc=Fn<Alloc>(rt,"boom_heap_alloc");var load=Fn<Mirror>(rt,"boom_mirror_load");var entry=Fn<Entry>(image,"boom_entry32");var field=Fn<Field>(rt,"boom_class_value_field");IntPtr[] classes=new IntPtr[ids.Length],maps=new IntPtr[ids.Length],arrays=new IntPtr[ids.Length],alternates=new IntPtr[ids.Length],otherArrays=new IntPtr[ids.Length];
            Func<IntPtr,IntPtr> read=cls=>{var c=new Context();IntPtr v=entry(ref c,new[]{Bits(cls)});Check(c.Kind==0&&c.Depth==0&&v!=IntPtr.Zero,"Original ClassValue cache read failed kind="+c.Kind+" method="+c.Method+" pc="+c.PC);return v;};
            Action<IntPtr,IntPtr> write=(cls,map)=>{var c=new Context();field(ref c,new[]{Bits(cls),Bits(map)},pool,1);Check(c.Kind==0,"ClassValue sidecar write failed: "+c.Kind);};
            string[] result=new string[ids.Length+1];
            for(int i=0;i<ids.Length;i++){
                var c=new Context();classes[i]=load(heap,mirrors,ids[i],ref c);Check(c.Kind==0&&classes[i]!=IntPtr.Zero,"ClassValue target mirror failed");IntPtr empty=read(classes[i]);
                arrays[i]=alloc(heap,256,32,Bits(Marshal.ReadIntPtr(empty,-8)));otherArrays[i]=alloc(heap,512,64,Bits(Marshal.ReadIntPtr(empty,-8)));maps[i]=alloc(heap,bytes,refs,Bits(tag));alternates[i]=alloc(heap,bytes,refs,Bits(tag));Check(arrays[i]!=IntPtr.Zero&&maps[i]!=IntPtr.Zero&&alternates[i]!=IntPtr.Zero&&otherArrays[i]!=IntPtr.Zero,"ClassValue VM fixture OOM");Marshal.WriteIntPtr(maps[i],(int)cacheOffset,arrays[i]);Marshal.WriteIntPtr(alternates[i],(int)cacheOffset,otherArrays[i]);
                bool stableEmpty=empty==read(classes[i]);write(classes[i],maps[i]);IntPtr populated=read(classes[i]);bool stable=populated==read(classes[i]);write(classes[i],IntPtr.Zero);result[i]=(Marshal.ReadInt64(empty,-16)/8)+"|"+stableEmpty.ToString().ToLowerInvariant()+"|"+(Marshal.ReadInt64(populated,-16)/8)+"|"+stable.ToString().ToLowerInvariant()+"|"+(empty!=populated).ToString().ToLowerInvariant()+"|"+(empty==read(classes[i])).ToString().ToLowerInvariant();write(classes[i],maps[i]);
            }
            var nullContext=new Context();Check(entry(ref nullContext,new[]{0UL})==IntPtr.Zero&&nullContext.Kind==16&&nullContext.Pending!=0&&nullContext.PC==1&&nullContext.Method==entryId,"ClassValue null did not preserve field failure location");Check(Marshal.ReadIntPtr(new IntPtr(unchecked((long)nullContext.Pending)),-8)==Fn<Indexed>(image,"boom_get_object_layout")(npeClass),"ClassValue null did not produce original NPE");result[ids.Length]="npe";
            long before=Marshal.ReadInt64(heap,48);Parallel.For(0,8,worker=>{int i=worker%ids.Length;for(int round=0;round<1024;round++){write(classes[i],(round&1)==0?maps[i]:alternates[i]);IntPtr v=read(classes[i]);Check(v==arrays[i]||v==otherArrays[i],"ClassValue pointer read was torn or lost type identity");}});Check(Marshal.ReadInt64(heap,48)==before,"Warm ClassValue access allocated guest objects");
            for(int i=0;i<ids.Length;i++)write(classes[i],maps[i]);
            foreign=Fn<Create>(rt,"boom_heap_create")(65536);IntPtr foreignMap=alloc(foreign,bytes,refs,Bits(tag));Check(foreignMap!=IntPtr.Zero,"Foreign VM fixture allocation failed");
            foreach(var bad in new[]{new[]{Bits(classes[0]),Bits(classes[1])},new[]{Bits(classes[0]),Bits(foreignMap)},new[]{Bits(maps[0]),Bits(maps[0])},new[]{1UL,Bits(maps[0])}}){var c=new Context();Check(field(ref c,bad,pool,1)==IntPtr.Zero&&c.Kind==7,"Invalid ClassValue receiver/value was accepted");Check(read(classes[0])==arrays[0],"Rejected write changed ClassValue root");}
            var pending=new Context{Kind=5,PC=91,Method=13,Pending=123};field(ref pending,new[]{Bits(classes[0]),0UL},pool,1);Check(pending.Kind==5&&pending.PC==91&&pending.Method==13&&pending.Pending==123&&read(classes[0])==arrays[0],"Pending ClassValue write changed state");
            IntPtr roots=Fn<Roots>(image,"boom_get_static_roots")(out uint count);Check(Fn<Collect>(rt,"boom_heap_collect")(heap,roots,count)!=ulong.MaxValue,"ClassValue roots were not collected safely");for(int i=0;i<ids.Length;i++)Check(read(classes[i])==arrays[i],"ClassValue cache graph was lost during quiescent collection");return result;
        } finally {if(image!=IntPtr.Zero&&GetProcAddress(image,"boom_release_trace_pool")!=IntPtr.Zero)Check(Fn<Release>(image,"boom_release_trace_pool")()==0,"ClassValue frames remain");if(foreign!=IntPtr.Zero)Fn<One>(rt,"boom_heap_destroy")(foreign);if(heap!=IntPtr.Zero)Fn<One>(rt,"boom_heap_destroy")(heap);if(rt!=IntPtr.Zero)FreeLibrary(rt);if(image!=IntPtr.Zero)FreeLibrary(image);}
    }
}
