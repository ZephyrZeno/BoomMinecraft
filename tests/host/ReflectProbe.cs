// Disposable controller for source-generated Java factories and assembly reflection.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomReflectProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context{public uint Kind,PC,Method,Depth;public ulong Pending,Plan;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)]static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")]static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Indexed(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Field(uint owner,uint field);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Load(IntPtr heap,IntPtr pool,uint id,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Entry(ref Context c,[In]ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Service(ref Context c,[In]ulong[] a,IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate uint Release();
    static void Check(bool v,string why){if(!v)throw new Exception(why);}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static ulong Bits(IntPtr p){return unchecked((ulong)p.ToInt64());}
    static void GC(IntPtr m,IntPtr heap,params IntPtr[] extra){IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n),all=Marshal.AllocHGlobal(checked(((int)n+extra.Length)*8));try{for(int i=0;i<n;i++)Marshal.WriteIntPtr(all,i*8,Marshal.ReadIntPtr(roots,i*8));for(int i=0;i<extra.Length;i++)Marshal.WriteIntPtr(all,((int)n+i)*8,extra[i]);Check(Fn<Collect>(m,"boom_heap_collect")(heap,all,n+(uint)extra.Length)!=ulong.MaxValue,"Reflection root collection failed");}finally{Marshal.FreeHGlobal(all);}}
    public static void Packaged(string image,string runtime,uint instantiationClass,uint noSuchClass,uint causeOffset){
        IntPtr m=LoadLibraryExW(image,IntPtr.Zero,0x1100),r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;Check(m!=IntPtr.Zero&&r!=IntPtr.Zero,"Packaged reflection DLL load failed");
        try{
            heap=Fn<Create>(r,"boom_heap_create")(1048576);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Packaged reflection heap bind failed");var entry=Fn<Entry>(m,"boom_entry32");var query=Fn<Service>(r,"boom_reflect_new");IntPtr pool=Fn<Pointer>(m,"boom_get_reflect_pool")();
            var warm=new Context();IntPtr mirror=entry(ref warm,new[]{0UL,0UL,0UL});Check(warm.Kind==0&&mirror!=IntPtr.Zero,"Packaged reflection mirror failed");var c=new Context{Plan=warm.Plan};IntPtr value=query(ref c,new[]{Bits(mirror)},pool);Check(c.Kind==0&&value!=IntPtr.Zero&&Marshal.ReadInt32(value)==42,"Packaged Java constructor differs");GC(m,heap,value);Check(Marshal.ReadInt32(value)==42,"Packaged constructor result lost");
            warm=new Context();mirror=entry(ref warm,new[]{2UL,0UL,0UL});c=new Context{Plan=warm.Plan};Check(query(ref c,new[]{Bits(mirror)},pool)==IntPtr.Zero&&c.Kind==16&&c.Pending!=0,"Packaged missing-constructor error differs");IntPtr error=new IntPtr(unchecked((long)c.Pending)),cause=Marshal.ReadIntPtr(error,(int)causeOffset);var layout=Fn<Indexed>(m,"boom_get_object_layout");Check(Marshal.ReadIntPtr(error,-8)==layout(instantiationClass)&&cause!=IntPtr.Zero&&Marshal.ReadIntPtr(cause,-8)==layout(noSuchClass),"Packaged reflection cause class differs");GC(m,heap,error);Check(Marshal.ReadIntPtr(error,(int)causeOffset)==cause,"Packaged reflection cause lost after GC");
        }finally{if(m!=IntPtr.Zero)Check(Fn<Release>(m,"boom_release_trace_pool")()==0,"Packaged reflection frames remain");if(heap!=IntPtr.Zero)Fn<One>(r,"boom_heap_destroy")(heap);if(r!=IntPtr.Zero)FreeLibrary(r);if(m!=IntPtr.Zero)FreeLibrary(m);}
    }
    public static string[] Run(string dll,uint[] ids,string[] names,uint[] valueOffsets,uint causeOffset,uint throwMethod,uint programId,uint countField,uint stringType){
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),heap=IntPtr.Zero,foreign=IntPtr.Zero;Check(m!=IntPtr.Zero,"Reflection DLL load failed");
        try{
            heap=Fn<Create>(m,"boom_heap_create")(8388608);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Reflection heap bind failed");
            var entry=Fn<Entry>(m,"boom_entry32");var query=Fn<Service>(m,"boom_reflect_new");var alloc=Fn<Alloc>(m,"boom_heap_alloc");var layout=Fn<Indexed>(m,"boom_get_object_layout");var descriptor=Fn<Indexed>(m,"boom_get_class_descriptor");var tags=new Dictionary<IntPtr,string>();for(int i=0;i<ids.Length;i++)tags[layout(ids[i])]=names[i];
            Func<IntPtr,string> name=value=>{Check(value!=IntPtr.Zero,"Null result/Throwable");IntPtr tag=Marshal.ReadIntPtr(value,-8);Check(tags.ContainsKey(tag),"Unknown result class tag");return tags[tag];};
            var warm=new Context();IntPtr mirror=entry(ref warm,new[]{0UL,0UL,0UL});Check(warm.Kind==0&&mirror!=IntPtr.Zero,"Cold Class literal failed");ulong plan=warm.Plan;IntPtr count=Fn<Field>(m,"boom_get_static_field")(programId,countField);Check(count!=IntPtr.Zero&&Marshal.ReadInt32(count)==0,"Class literal ran target initializer");IntPtr valueDesc=descriptor(ids[Array.IndexOf(names,"dev.boom.reflect.ReflectProgram$Value")]);Check(Marshal.ReadInt32(valueDesc,8)==0,"Class literal initialized target early");
            var parallelValues=new IntPtr[1024];System.Threading.Tasks.Parallel.For(0,8,new System.Threading.Tasks.ParallelOptions{MaxDegreeOfParallelism=8},worker=>{for(int j=0;j<128;j++){var c=new Context();IntPtr value=entry(ref c,new[]{0UL,0UL,1UL});Check(c.Kind==0&&c.Depth==0&&name(value)=="dev.boom.reflect.ReflectProgram$Value"&&Marshal.ReadInt32(value,(int)valueOffsets[Array.IndexOf(names,"dev.boom.reflect.ReflectProgram$Value")])==42,"Concurrent cold reflection failed");parallelValues[worker*128+j]=value;}});Check(new HashSet<IntPtr>(parallelValues).Count==parallelValues.Length&&Marshal.ReadInt32(valueDesc,8)==2,"Concurrent reflection identity/initialization differs");Check(Marshal.ReadInt32(count)==1,"Target initializer did not execute exactly once");
            var results=new List<string>();IntPtr marker=IntPtr.Zero;
            for(uint kind=0;kind<=11;kind++)for(uint route=0;route<3;route++){
                var c=new Context();IntPtr value=entry(ref c,new[]{(ulong)kind,(ulong)route,1UL});Check(c.Depth==0,"Reflection leaked Java frame");
                if(c.Kind==0){string type=name(value);int index=Array.IndexOf(names,type);int score=type=="java.lang.Object"?0:Marshal.ReadInt32(value,(int)valueOffsets[index]);results.Add(kind+" "+route+" v "+type+" "+score);GC(m,heap,value);Check(name(value)==type,"Reflected object lost after collection");}
                else{Check(c.Kind==16&&c.Pending!=0&&value==IntPtr.Zero,"Reflection exception not materialized: "+c.Kind);IntPtr pending=new IntPtr(unchecked((long)c.Pending));IntPtr cause=Marshal.ReadIntPtr(pending,(int)causeOffset);string type=name(pending),causeType=cause==IntPtr.Zero||cause==pending?"-":name(cause);results.Add(kind+" "+route+" e "+type+" "+causeType);
                    if(kind==9){Check(type=="dev.boom.reflect.ReflectProgram$Marker"&&c.Method==throwMethod&&c.PC==7,"Constructor Throwable source location changed: "+c.Method+"/"+c.PC);if(marker==IntPtr.Zero)marker=pending;else Check(marker==pending,"Constructor Throwable was wrapped/copied");}
                    GC(m,heap,pending);Check(name(pending)==type,"Reflection Throwable/cause root lost");}
                GC(m,heap);
            }
            var pendingContext=new Context{Kind=23,PC=91,Method=37,Depth=2,Pending=0x1234,Plan=0x5678};Check(query(ref pendingContext,null,IntPtr.Zero)==IntPtr.Zero&&pendingContext.Kind==23&&pendingContext.PC==91&&pendingContext.Method==37&&pendingContext.Depth==2&&pendingContext.Pending==0x1234&&pendingContext.Plan==0x5678,"Pending reflection context changed");
            IntPtr pool=Fn<Pointer>(m,"boom_get_reflect_pool")();var raw=new Context{Plan=plan};Check(query(ref raw,new[]{0UL},pool)==IntPtr.Zero&&raw.Kind==4,"Null reflection receiver differs");
            raw=new Context{Plan=plan};IntPtr wrong=alloc(heap,8,0,267);Check(query(ref raw,new[]{Bits(wrong)},pool)==IntPtr.Zero&&raw.Kind==7,"Non-Class accepted by reflection");
            foreign=Fn<Create>(m,"boom_heap_create")(4096);IntPtr foreignValue=alloc(foreign,8,0,Bits(Marshal.ReadIntPtr(Marshal.ReadIntPtr(pool,8),32)));Marshal.WriteInt64(foreignValue,Marshal.ReadInt64(mirror));raw=new Context{Plan=plan};Check(query(ref raw,new[]{Bits(foreignValue)},pool)==IntPtr.Zero&&raw.Kind==7,"Foreign mirror accepted");
            raw=new Context{Plan=plan};IntPtr stringMirror=Fn<Load>(m,"boom_mirror_load")(heap,Marshal.ReadIntPtr(pool,8),stringType,ref raw);Check(raw.Kind==0&&stringMirror!=IntPtr.Zero,"String mirror fixture failed");raw=new Context{Plan=plan};Check(query(ref raw,new[]{Bits(stringMirror)},pool)==IntPtr.Zero&&raw.Kind==20,"Unlinked constructor was silently simulated");
            IntPtr badPool=Marshal.AllocHGlobal(80);try{byte[] bytes=new byte[80];Marshal.Copy(pool,bytes,0,80);Marshal.Copy(bytes,0,badPool,80);Marshal.WriteInt32(badPool,44,1);raw=new Context{Plan=plan};Check(query(ref raw,new[]{Bits(mirror)},badPool)==IntPtr.Zero&&raw.Kind==7,"Bad reflection flags accepted");}finally{Marshal.FreeHGlobal(badPool);}
            GC(m,heap,mirror);while(alloc(heap,4096,0,267)!=IntPtr.Zero){}while(alloc(heap,0,0,267)!=IntPtr.Zero){}raw=new Context{Plan=plan,PC=19,Method=2};Check(query(ref raw,new[]{Bits(mirror)},pool)==IntPtr.Zero&&raw.Kind==16&&name(new IntPtr(unchecked((long)raw.Pending)))=="java.lang.OutOfMemoryError"&&raw.PC==19&&raw.Method==2,"Reflection allocation OOM/source differs");GC(m,heap,mirror);raw=new Context{Plan=plan};IntPtr recovered=query(ref raw,new[]{Bits(mirror)},pool);Check(raw.Kind==0&&name(recovered)=="dev.boom.reflect.ReflectProgram$Value","Reflection failed after explicit reclamation");
            return results.ToArray();
        }finally{Check(Fn<Release>(m,"boom_release_trace_pool")()==0,"Active reflection frames at shutdown");if(foreign!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(foreign);if(heap!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(heap);FreeLibrary(m);}
    }
}
