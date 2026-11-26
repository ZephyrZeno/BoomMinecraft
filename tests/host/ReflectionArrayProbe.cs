// Test controller only. Allocation, type checks, exceptions and collection are
// native MASM. The traversal below measures the resulting guest object graph.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
public static class BoomReflectionArrayProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {public uint Kind,PC,Method,Depth;public ulong Pending,Plan;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong bytes,uint refs,IntPtr tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Entry(ref Context c,[In] ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Query(ref Context c,[In] ulong[] a,IntPtr p,uint op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr GetClass(ref Context c,[In] ulong[] a,IntPtr h,IntPtr map);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Mirror(IntPtr h,IntPtr p,uint id,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Static(uint owner,uint field);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Close();
    static void Check(bool v,string why){if(!v)throw new Exception(why);}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static ulong Bits(IntPtr p){return unchecked((ulong)p.ToInt64());}
    sealed class Vector {
        public string Component,Expected; public uint Operation,Kind; public int[] Counts; public ulong Arrays,Bytes;
        public static Vector Parse(string line){string[] p=line.Split('|');return new Vector{Component=p[0],Operation=uint.Parse(p[1]),Counts=p[2]=="null"?null:p[2].Length==0?Array.Empty<int>():Array.ConvertAll(p[2].Split(','),int.Parse),Kind=uint.Parse(p[3]),Expected=p[4],Arrays=ulong.Parse(p[5]),Bytes=ulong.Parse(p[6])};}
    }
    sealed class Image {
        public IntPtr Module,Heap,Pool,Map,Mirrors; public string[] Names; public Dictionary<string,uint> Types; public Entry Entry; public Query Query; public Alloc Alloc; public GetClass GetClass; public Mirror Mirror;
        public IntPtr Class(string descriptor){if(descriptor=="null")return IntPtr.Zero;var c=new Context();IntPtr p=Mirror(Heap,Mirrors,Types[descriptor],ref c);Check(p!=IntPtr.Zero&&c.Kind==0,"Missing canonical mirror "+descriptor);return p;}
        public string Type(IntPtr value){var c=new Context();IntPtr p=GetClass(ref c,new[]{Bits(value)},Heap,Map);Check(p!=IntPtr.Zero&&c.Kind==0,"getClass failed: "+c.Kind);long id=Marshal.ReadInt64(p);Check(id>=0&&id<Names.Length,"Invalid mirrored runtime type");return Names[id];}
        public IntPtr Dimensions(int[] counts,IntPtr heap){if(counts==null)return IntPtr.Zero;IntPtr p=Alloc(heap,(ulong)counts.Length*4,0,new IntPtr(266));Check(p!=IntPtr.Zero,"Dimension input allocation failed");Marshal.Copy(counts,0,p,counts.Length);return p;}
        public void Measure(IntPtr value,HashSet<IntPtr> seen,ref ulong arrays,ref ulong bytes){
            Check(value!=IntPtr.Zero&&seen.Add(value),"Aliased or null allocated child array");string name=Type(value);Check(name.StartsWith("["),"Result is not an array");ulong payload=(ulong)Marshal.ReadInt64(value,-16);uint refs=(uint)Marshal.ReadInt32(value,-20);arrays++;bytes+=payload;
            bool reference=name[1]=='['||name[1]=='L';
            if(reference){Check(payload==(ulong)refs*8,"Reference array scan prefix differs");for(uint i=0;i<refs;i++){IntPtr child=Marshal.ReadIntPtr(value,checked((int)i*8));if(child!=IntPtr.Zero)Measure(child,seen,ref arrays,ref bytes);}}
            else{Check(refs==0,"Primitive array has reference prefix");for(ulong i=0;i<payload;i++)Check(Marshal.ReadByte(value,checked((int)i))==0,"New primitive array is not zeroed");}
        }
        public void Result(IntPtr value,Vector v,bool caught){
            Check(value!=IntPtr.Zero,"Missing source result");if(v.Kind!=0){Check(caught&&Type(value)==v.Expected,"Caught exception type differs: "+v.Expected);return;}
            if(v.Operation>=2){Check(value==Class(v.Component)&&v.Expected==v.Component,"asSubclass changed Class identity");return;}
            Check(Type(value)==v.Expected,"Allocated array type differs: "+v.Expected);ulong arrays=0,bytes=0;Measure(value,new HashSet<IntPtr>(),ref arrays,ref bytes);Check(arrays==v.Arrays&&bytes==v.Bytes,"Allocated dimension graph differs for "+v.Component);
        }
        public void Sample(Vector v){
            IntPtr component=Class(v.Component),dims=v.Operation==1?Dimensions(v.Counts,Heap):IntPtr.Zero;
            ulong second=v.Operation==0?unchecked((ulong)(long)v.Counts[0]):Bits(dims);
            if(v.Operation<2){var raw=new Context();IntPtr value=Query(ref raw,new[]{Bits(component),second},Pool,v.Operation);Check(raw.Kind==v.Kind,"Native error priority differs for "+v.Component+" op="+v.Operation+" expected="+v.Kind+" actual="+raw.Kind);if(v.Kind==0)Result(value,v,false);else Check(value==IntPtr.Zero,"Failed allocation returned an object");}
            var c=new Context();uint mode=v.Operation==0?0:v.Operation==1?3:v.Operation+2;
            IntPtr result=Entry(ref c,new[]{Bits(component),v.Operation==0?second:0UL,Bits(dims),(ulong)mode});Check(c.Kind==0&&c.Depth==0&&c.Pending==0,"Source API/catch path failed: "+c.Kind);Result(result,v,true);
        }
        public ulong Collection(){IntPtr roots=Fn<Roots>(Module,"boom_get_static_roots")(out uint n);var seen=new HashSet<IntPtr>();var todo=new Stack<IntPtr>();for(int i=0;i<n;i++)todo.Push(Marshal.ReadIntPtr(roots,i*8));while(todo.Count>0){IntPtr p=todo.Pop();if(p==IntPtr.Zero||!seen.Add(p))continue;uint refs=(uint)Marshal.ReadInt32(p,-20);for(uint i=0;i<refs;i++)todo.Push(Marshal.ReadIntPtr(p,checked((int)i*8)));}ulong reclaimed=Fn<Collect>(Module,"boom_heap_collect")(Heap,roots,n);Check(reclaimed!=ulong.MaxValue&&(ulong)Marshal.ReadInt64(Heap,56)==(ulong)seen.Count,"Quiescent array graph collection differs");return reclaimed;}
        public void PartialOom(){
            Collection();IntPtr dims=Dimensions(new[]{2,100},Heap),component=Class("I");
            IntPtr reserve=Alloc(Heap,480,0,new IntPtr(266));Check(reserve!=IntPtr.Zero,"OOM gap reserve failed");var fillers=new List<IntPtr>();
            foreach(ulong bytes in new[]{1048576UL,4096UL,0UL})while(true){IntPtr p=Alloc(Heap,bytes,0,new IntPtr(266));if(p==IntPtr.Zero)break;fillers.Add(p);Check(fillers.Count<100000,"Unbounded heap fill fixture");}
            IntPtr statics=Fn<Roots>(Module,"boom_get_static_roots")(out uint n),roots=Marshal.AllocHGlobal(checked(((int)n+fillers.Count+1)*8));
            try{for(int i=0;i<n;i++)Marshal.WriteIntPtr(roots,i*8,Marshal.ReadIntPtr(statics,i*8));for(int i=0;i<fillers.Count;i++)Marshal.WriteIntPtr(roots,((int)n+i)*8,fillers[i]);Marshal.WriteIntPtr(roots,((int)n+fillers.Count)*8,dims);Check(Fn<Collect>(Module,"boom_heap_collect")(Heap,roots,n+(uint)fillers.Count+1)==1&&(ulong)Marshal.ReadInt64(Heap,80)==512,"Reserved OOM hole did not reclaim exactly one block");}finally{Marshal.FreeHGlobal(roots);}
            ulong before=(ulong)Marshal.ReadInt64(Heap,48);var c=new Context();Check(Query(ref c,new[]{Bits(component),Bits(dims)},Pool,1)==IntPtr.Zero&&c.Kind==3,"Partial multi-array allocation must fail with OOM");Check((ulong)Marshal.ReadInt64(Heap,48)-before==480,"OOM did not occur after parent and first child publication");Check(Collection()>(ulong)fillers.Count,"Partial array graph and fillers were not reclaimed");
            var retry=new Context();Check(Query(ref retry,new[]{Bits(component),1UL},Pool,0)!=IntPtr.Zero&&retry.Kind==0,"Allocation did not recover after explicit collection");
        }
    }
    public static void Run(string dll,string vectors,string[] descriptors,uint owner,uint initializedField,uint missingType){
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),heap=IntPtr.Zero,foreign=IntPtr.Zero,copy=IntPtr.Zero;Check(m!=IntPtr.Zero,"Reflection array image load failed");
        try{
            heap=Fn<Create>(m,"boom_heap_create")(16777216);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Reflection heap bind failed");IntPtr pool=Fn<Pointer>(m,"boom_get_reflect_array_pool")();
            var image=new Image{Module=m,Heap=heap,Pool=pool,Map=Marshal.ReadIntPtr(pool,32),Mirrors=Marshal.ReadIntPtr(pool,16),Names=descriptors,Types=new Dictionary<string,uint>(),Entry=Fn<Entry>(m,"boom_entry32"),Query=Fn<Query>(m,"boom_reflect_array_allocate"),Alloc=Fn<Alloc>(m,"boom_heap_alloc"),GetClass=Fn<GetClass>(m,"boom_runtime_getclass"),Mirror=Fn<Mirror>(m,"boom_mirror_load")};
            for(uint i=0;i<descriptors.Length;i++)image.Types.Add(descriptors[i],i);
            var pending=new Context{Kind=23,PC=91,Method=37,Depth=2,Pending=0x1234,Plan=0x5678};Check(image.Query(ref pending,null,IntPtr.Zero,99)==IntPtr.Zero&&pending.Kind==23&&pending.PC==91&&pending.Method==37&&pending.Depth==2&&pending.Pending==0x1234&&pending.Plan==0x5678,"Pending allocation context changed");
            var cases=new List<Vector>();foreach(string line in File.ReadAllLines(vectors)){Vector v=Vector.Parse(line);image.Sample(v);cases.Add(v);}
            Check(cases.Count==386,"JVM vector scope changed");
            var light=cases.FindAll(v=>v.Kind==0&&v.Operation<2&&v.Component.Length<80&&v.Counts!=null&&v.Counts.Length<=2);Check(light.Count>20,"Insufficient parallel source cases");
            System.Threading.Tasks.Parallel.For(0,8,new System.Threading.Tasks.ParallelOptions{MaxDegreeOfParallelism=8},worker=>{for(int i=0;i<512;i++)image.Sample(light[(worker*31+i)%light.Count]);});
            Check(Marshal.ReadInt32(Fn<Static>(m,"boom_get_static_field")(owner,initializedField))==0,"Reflection initialized the component class");
            Check(image.Collection()>0,"Temporary array graphs were not reclaimed");
            IntPtr intClass=image.Class("I"),missing=image.Class(descriptors[missingType]);var unsupported=new Context();Check(image.Query(ref unsupported,new[]{Bits(missing),0UL},pool,0)==IntPtr.Zero&&unsupported.Kind==7,"Absent exact array type silently changed component identity");
            var huge=new Context();Check(image.Query(ref huge,new[]{Bits(intClass),2147483647UL},pool,0)==IntPtr.Zero&&huge.Kind==3,"Oversized array did not report OOM");
            var wrong=new Context();Check(image.Query(ref wrong,new[]{Bits(intClass),Bits(intClass)},pool,1)==IntPtr.Zero&&wrong.Kind==7,"Wrong dimension object type accepted");
            foreign=Fn<Create>(m,"boom_heap_create")(4096);IntPtr alien=image.Dimensions(new[]{1},foreign);var outside=new Context();Check(image.Query(ref outside,new[]{Bits(intClass),Bits(alien)},pool,1)==IntPtr.Zero&&outside.Kind==7,"Foreign heap dimensions accepted");
            copy=Marshal.AllocHGlobal(48);var bytes=new byte[48];Marshal.Copy(pool,bytes,0,48);Marshal.Copy(bytes,0,copy,48);Marshal.WriteInt32(copy,44,1);var malformed=new Context();Check(image.Query(ref malformed,new[]{Bits(intClass),1UL},copy,0)==IntPtr.Zero&&malformed.Kind==7,"Malformed reflection pool accepted");
            image.PartialOom();image.Collection();
        }finally{if(m!=IntPtr.Zero){Fn<Close>(m,"boom_release_trace_pool")();if(foreign!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(foreign);if(heap!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(heap);if(copy!=IntPtr.Zero)Marshal.FreeHGlobal(copy);FreeLibrary(m);}}
    }
}
