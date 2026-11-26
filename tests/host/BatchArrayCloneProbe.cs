using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;

// Development host only. Allocation, typing, cloning, synchronization and
// explicit collection run MASM; source-shaped arrays need no Java constructor.
public static class BoomBatchArrayCloneProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Make(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr NewArray(IntPtr heap,IntPtr counts,IntPtr type,uint dimensions,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Clone(IntPtr ctx,IntPtr argv);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Literal(IntPtr ctx,IntPtr pool,uint index);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr TypeOf(IntPtr value,IntPtr map,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Collect(IntPtr heap,IntPtr roots,ulong count);
    sealed class Site {public string Symbol,Descriptor;public int Type;public Clone Function;public IntPtr Source,Copy;}
    static void Need(bool value,string message){if(!value)throw new Exception(message);}
    static T Symbol<T>(IntPtr m,string name) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(m,name));}
    static void Reset(IntPtr ctx){for(int i=0;i<32;i+=8)Marshal.WriteInt64(ctx,i,0);Marshal.WriteInt32(ctx,4,37);Marshal.WriteInt32(ctx,8,73);}
    static void Error(IntPtr ctx,int kind){Need(Marshal.ReadInt32(ctx)==kind&&Marshal.ReadInt32(ctx,4)==37&&Marshal.ReadInt32(ctx,8)==73&&Marshal.ReadInt32(ctx,12)==0,"Clone error/location contract differs");}
    static void Compare(IntPtr source,IntPtr clone,IntPtr ctx,TypeOf query,IntPtr map){
        Need(clone!=IntPtr.Zero&&clone!=source&&Marshal.ReadInt32(ctx)==0,"Clone allocation failed");
        Need(Marshal.ReadInt64(source,-8)==Marshal.ReadInt64(clone,-8)&&Marshal.ReadInt32(source,-20)==Marshal.ReadInt32(clone,-20),"Clone runtime tag/reference prefix changed");
        int bytes=checked((int)Marshal.ReadInt64(source,-16));Need(Marshal.ReadInt64(clone,-16)==bytes,"Clone length changed");
        Need(query(source,map,ctx)==query(clone,map,ctx)&&Marshal.ReadInt32(ctx)==0,"Clone exact source runtime type changed");
        for(int i=0;i<bytes;i++)Need(Marshal.ReadByte(source,i)==Marshal.ReadByte(clone,i),"Clone raw payload changed");
    }
    public static long[] Run(string runtime,string dll,string directory,int objectId){
        IntPtr library=NativeLibrary.Load(runtime),module=IntPtr.Zero,heap=IntPtr.Zero,ctx=IntPtr.Zero,args=IntPtr.Zero,counts=IntPtr.Zero,rootMemory=IntPtr.Zero;
        var destroy=Symbol<Destroy>(library,"boom_heap_destroy");
        try{
            module=NativeLibrary.Load(dll);ctx=Marshal.AllocHGlobal(32);args=Marshal.AllocHGlobal(8);counts=Marshal.AllocHGlobal(16);Reset(ctx);
            heap=Symbol<Create>(library,"boom_heap_create")(64*1024*1024);Need(heap!=IntPtr.Zero&&Symbol<Bind>(module,"boom_java_string_literals_bind_heap")(heap)==1,"Clone heap bind failed");
            var make=Symbol<Make>(library,"boom_object_new");var allocate=Symbol<NewArray>(library,"boom_typed_multi_new");
            var query=Symbol<TypeOf>(library,"boom_runtime_type");var collect=Symbol<Collect>(library,"boom_heap_collect");
            IntPtr map=NativeLibrary.GetExport(module,"boom_runtime_type_map"),types=NativeLibrary.GetExport(module,"boom_batch_type_descriptors"),rows=Marshal.ReadIntPtr(map,16),objectLayout=IntPtr.Zero;
            for(int i=0;i<Marshal.ReadInt32(map,8);i++){IntPtr row=IntPtr.Add(rows,i*40);if(Marshal.ReadInt32(row,16)==objectId){objectLayout=Marshal.ReadIntPtr(row);break;}}
            Need(objectLayout!=IntPtr.Zero,"Object source layout missing");IntPtr plain=make(heap,objectLayout,ctx);
            IntPtr text=Symbol<Literal>(module,"boom_java_string_literal")(ctx,NativeLibrary.GetExport(module,"boom_java_string_literal_pool"),0);
            Need(plain!=IntPtr.Zero&&text!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Clone reference seed failed");
            var retained=new List<IntPtr>{plain,text};var sites=new List<Site>();var ids=new HashSet<int>();long nested=0,payloadBytes=0,nonNull=0;
            Site objects=null,strings=null,bytesSite=null,ints=null;
            foreach(string line in File.ReadLines(Path.Combine(directory,"clones.tsv"))){
                string[] p=line.Split('\t');var site=new Site{Symbol=p[0],Type=int.Parse(p[1]),Descriptor=p[2],Function=Symbol<Clone>(module,p[0])};
                Reset(ctx);Marshal.WriteInt64(counts,3);Marshal.WriteInt64(counts,8,3);uint dimensions=site.Descriptor.StartsWith("[[",StringComparison.Ordinal)?2u:1u;
                site.Source=allocate(heap,counts,Marshal.ReadIntPtr(types,site.Type*8),dimensions,ctx);
                Need(site.Source!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Source array allocation failed: "+site.Descriptor);
                if(Marshal.ReadInt32(site.Source,-20)==0){int size=checked((int)Marshal.ReadInt64(site.Source,-16));for(int i=0;i<size;i++)Marshal.WriteByte(site.Source,i,site.Descriptor=="[Z"?(byte)(i&1):unchecked((byte)(i*67+site.Type)));}
                else if(site.Descriptor=="[Ljava/lang/Object;"){Marshal.WriteIntPtr(site.Source,plain);Marshal.WriteIntPtr(site.Source,8,text);nonNull++;}
                else if(site.Descriptor=="[Ljava/lang/String;"){Marshal.WriteIntPtr(site.Source,text);Marshal.WriteIntPtr(site.Source,8,text);nonNull++;}
                if(dimensions==2)nested++;
                Marshal.WriteIntPtr(args,site.Source);site.Copy=site.Function(ctx,args);Compare(site.Source,site.Copy,ctx,query,map);
                payloadBytes+=Marshal.ReadInt64(site.Source,-16);
                if(Marshal.ReadInt32(site.Source,-20)>0){IntPtr value=Marshal.ReadIntPtr(site.Source);Marshal.WriteIntPtr(site.Copy,IntPtr.Zero);Need(Marshal.ReadIntPtr(site.Source)==value,"Editing clone reference changed original");Marshal.WriteIntPtr(site.Copy,value);}
                else{byte value=Marshal.ReadByte(site.Source);Marshal.WriteByte(site.Copy,(byte)(value^1));Need(Marshal.ReadByte(site.Source)==value,"Editing clone primitive changed original");Marshal.WriteByte(site.Copy,value);}
                retained.Add(site.Source);retained.Add(site.Copy);sites.Add(site);ids.Add(site.Type);
                if(site.Descriptor=="[Ljava/lang/Object;")objects=site;if(site.Descriptor=="[Ljava/lang/String;")strings=site;if(site.Descriptor=="[B")bytesSite=site;if(site.Descriptor=="[I")ints=site;
            }
            Need(objects!=null&&strings!=null&&bytesSite!=null&&ints!=null,"Required primitive/reference clone contracts missing");
            // Covariance must preserve the actual String[] tag at an Object[] site.
            Reset(ctx);Marshal.WriteIntPtr(args,strings.Source);IntPtr covariant=objects.Function(ctx,args);Compare(strings.Source,covariant,ctx,query,map);retained.Add(covariant);
            const int workers=8,rounds=1024;
            Parallel.For(0,workers,worker=>{IntPtr context=Marshal.AllocHGlobal(32),arguments=Marshal.AllocHGlobal(8);
                try{for(int i=0;i<rounds;i++){Site s=(i&1)==0?objects:ints;Reset(context);Marshal.WriteIntPtr(arguments,s.Source);IntPtr value=s.Function(context,arguments);Compare(s.Source,value,context,query,map);}}
                finally{Marshal.FreeHGlobal(context);Marshal.FreeHGlobal(arguments);}});
            int errors=0;Reset(ctx);Marshal.WriteIntPtr(args,IntPtr.Zero);Need(objects.Function(ctx,args)==IntPtr.Zero,"Null clone succeeded");Error(ctx,4);errors++;
            Reset(ctx);Marshal.WriteIntPtr(args,plain);Need(objects.Function(ctx,args)==IntPtr.Zero,"Object passed array clone");Error(ctx,7);errors++;
            Reset(ctx);Marshal.WriteIntPtr(args,bytesSite.Source);Need(ints.Function(ctx,args)==IntPtr.Zero,"Wrong primitive array passed clone");Error(ctx,7);errors++;
            Reset(ctx);Need(objects.Function(ctx,IntPtr.Zero)==IntPtr.Zero,"Null argument vector passed clone");Error(ctx,7);errors++;
            Reset(ctx);Marshal.WriteInt32(ctx,16);Marshal.WriteInt64(ctx,16,text.ToInt64());Marshal.WriteIntPtr(args,objects.Source);
            Need(objects.Function(ctx,args)==IntPtr.Zero&&Marshal.ReadIntPtr(ctx,16)==text,"Pending exception was consumed");Error(ctx,16);errors++;
            Reset(ctx);Marshal.WriteInt64(counts,32*1024*1024);IntPtr large=allocate(heap,counts,Marshal.ReadIntPtr(types,bytesSite.Type*8),1,ctx);
            Need(large!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"OOM source allocation failed");retained.Add(large);Marshal.WriteIntPtr(args,large);
            Need(bytesSite.Function(ctx,args)==IntPtr.Zero,"Oversized clone unexpectedly fit heap");Error(ctx,3);errors++;
            rootMemory=Marshal.AllocHGlobal(retained.Count*8);for(int i=0;i<retained.Count;i++)Marshal.WriteIntPtr(rootMemory,i*8,retained[i]);
            long freed=collect(heap,rootMemory,(ulong)retained.Count);Need(freed>=workers*rounds,"Unrooted parallel clones were not reclaimed");
            Reset(ctx);foreach(Site site in sites)Compare(site.Source,site.Copy,ctx,query,map);
            Need(Marshal.ReadIntPtr(objects.Source)==plain&&Marshal.ReadIntPtr(objects.Copy,8)==text,"Rooted shallow reference graph was lost");
            return new long[]{sites.Count,ids.Count,payloadBytes,nested,nonNull,workers*rounds,workers,errors,freed};
        }finally{if(rootMemory!=IntPtr.Zero)Marshal.FreeHGlobal(rootMemory);foreach(IntPtr p in new IntPtr[]{ctx,args,counts})if(p!=IntPtr.Zero)Marshal.FreeHGlobal(p);if(heap!=IntPtr.Zero)destroy(heap);if(module!=IntPtr.Zero)NativeLibrary.Free(module);NativeLibrary.Free(library);}
    }
}
