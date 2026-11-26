using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;

// Development caller only. OS queries, normal String/array construction,
// snapshot publication, original Java execution and collection all run MASM.
public static class BoomJavaPropertiesProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Materialize(IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr heap,ulong bytes,uint refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Make(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Native(IntPtr ctx,IntPtr args,IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Entry(IntPtr ctx,IntPtr args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Copy(IntPtr ctx,IntPtr pool,IntPtr chars,uint length);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr NewArray(IntPtr ctx,IntPtr pool,int count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Collect(IntPtr heap,IntPtr regions,ulong count);
    sealed class Data {
        public int Raw,Array,FieldOffset; public string[] Text,Names;
        public int[][] Rows,Pairs; public int[] Fallbacks;
    }
    static T Fn<T>(IntPtr m,string name) where T:Delegate {return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(m,name));}
    static void Need(bool ok,string message){if(!ok)throw new Exception(message);}
    static void Stage(string directory,string stage){File.AppendAllText(Path.Combine(directory,"execution-stages.log"),stage+"\n");}
    static void Reset(IntPtr p){for(int i=0;i<32;i+=8)Marshal.WriteInt64(p,i,0);Marshal.WriteInt32(p,4,37);Marshal.WriteInt32(p,8,73);}
    static IntPtr Memory(List<IntPtr> list,int bytes){IntPtr p=Marshal.AllocHGlobal(bytes);for(int i=0;i<bytes;i++)Marshal.WriteByte(p,i,0);list.Add(p);return p;}
    static string ReadText(BinaryReader r){int n=r.ReadInt32();Need(n>=0&&n<=65535,"Bad property case text");char[] a=new char[n];for(int i=0;i<n;i++)a[i]=(char)r.ReadUInt16();return new string(a);}
    static Data ReadData(string file){
        var d=new Data();using(var r=new BinaryReader(File.OpenRead(file))){
            Need(r.ReadInt32()==0x50524f42,"Bad source property case header");d.Raw=r.ReadInt32();d.Array=r.ReadInt32();d.FieldOffset=r.ReadInt32();
            d.Text=new string[r.ReadInt32()];for(int i=0;i<d.Text.Length;i++)d.Text[i]=ReadText(r);
            int count=r.ReadInt32();Need(count==39,"Incomplete platform schema");d.Rows=new int[count][];d.Names=new string[count];
            for(int i=0;i<count;i++){d.Rows[i]=new[]{r.ReadInt32(),r.ReadInt32(),r.ReadInt32(),r.ReadInt32()};d.Names[i]=ReadText(r);Need(d.Rows[i][0]==i,"Platform order differs");}
            d.Pairs=new int[r.ReadInt32()][];for(int i=0;i<d.Pairs.Length;i++)d.Pairs[i]=new[]{r.ReadInt32(),r.ReadInt32()};
            d.Fallbacks=new int[r.ReadInt32()];for(int i=0;i<d.Fallbacks.Length;i++)d.Fallbacks[i]=r.ReadInt32();Need(r.BaseStream.Position==r.BaseStream.Length,"Trailing source cases");
        }return d;
    }
    static int BE(BinaryReader r){return (r.ReadByte()<<24)|(r.ReadByte()<<16)|(r.ReadByte()<<8)|r.ReadByte();}
    static string[] Oracle(string file,Data d){
        var result=new string[39];using(var r=new BinaryReader(File.OpenRead(file))){
            Need(BE(r)==0x50524f50&&BE(r)==1&&BE(r)==39,"Bad JVM property oracle header");
            for(int i=0;i<39;i++){
                int n=(r.ReadByte()<<8)|r.ReadByte();string name=System.Text.Encoding.UTF8.GetString(r.ReadBytes(n));Need(name==d.Names[i],"JVM property index differs");
                int count=BE(r);if(count==-1){result[i]=null;continue;}Need(count>=0&&count<=65535,"Bad JVM property text length");
                char[] chars=new char[count];for(int j=0;j<count;j++)chars[j]=(char)((r.ReadByte()<<8)|r.ReadByte());result[i]=new string(chars);
            }Need(r.BaseStream.Position==r.BaseStream.Length,"Trailing JVM properties");
        }return result;
    }
    static string Text(IntPtr p,IntPtr literals){
        if(p==IntPtr.Zero)return null;
        Need(Marshal.ReadIntPtr(p,-8)==Marshal.ReadIntPtr(literals,40),"Property String has opaque/wrong source type tag");
        IntPtr bytes=Marshal.ReadIntPtr(p,Marshal.ReadInt32(literals,48));int coder=Marshal.ReadByte(p,Marshal.ReadInt32(literals,52));
        Need(bytes!=IntPtr.Zero&&coder<=1&&Marshal.ReadInt64(bytes,-8)==264,"Property String value/coder/type differs");
        int size=checked((int)Marshal.ReadInt64(bytes,-16));Need(coder==0||size%2==0,"Odd UTF16 payload");char[] chars=new char[size>>coder];
        for(int i=0;i<chars.Length;i++)chars[i]=coder==0?(char)Marshal.ReadByte(bytes,i):(char)unchecked((ushort)Marshal.ReadInt16(bytes,i*2));
        uint hash=0;foreach(char c in chars)hash=unchecked(hash*31+c);
        Need(unchecked((uint)Marshal.ReadInt32(p,Marshal.ReadInt32(literals,56)))==hash,"Property String hash differs");return new string(chars);
    }
    static void Array(IntPtr value,IntPtr type,int count){Need(value!=IntPtr.Zero&&Marshal.ReadIntPtr(value,-8)==type&&Marshal.ReadInt64(value,-16)==count*8L&&Marshal.ReadInt32(value,-20)==count,"Property array is not a normal source String[]");}
    static IntPtr Call(Native raw,Entry entry,IntPtr ctx,IntPtr args,IntPtr pool){Reset(ctx);IntPtr p=entry==null?raw(ctx,args,pool):entry(ctx,args);Need(p!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Property call failed, kind="+Marshal.ReadInt32(ctx));return p;}
    static long Fill(Alloc allocate,IntPtr heap){long n=0;while(allocate(heap,4096,0,264)!=IntPtr.Zero)n++;while(allocate(heap,0,0,264)!=IntPtr.Zero)n++;return n;}
    static long GC(Collect collect,IntPtr heap,IntPtr regions,IntPtr properties,int propertyCount,IntPtr source,IntPtr statics,long staticCount,IntPtr caller){
        IntPtr[] pp={properties,Marshal.ReadIntPtr(source,24),statics,caller};long[] nn={propertyCount,Marshal.ReadInt32(source,8)*2L,staticCount,4};
        for(int i=0;i<pp.Length;i++){Marshal.WriteIntPtr(regions,i*16,pp[i]);Marshal.WriteInt64(regions,i*16+8,nn[i]);}
        long n=collect(heap,regions,4);Need(n>=0,"Property root-region collection failed");return n;
    }
    public static long[] Run(string runtime,string dll,string directory,string platformName=null,string vmName=null,string ctorName=null,string getterName=null){
        Data d=ReadData(Path.Combine(directory,"properties-cases.bin"));string[] expected=Oracle(Path.Combine(directory,"platform-oracle.bin"),d);
        IntPtr lib=NativeLibrary.Load(runtime),image=IntPtr.Zero,heap=IntPtr.Zero;var memory=new List<IntPtr>();
        var destroy=Fn<Destroy>(lib,"boom_heap_destroy");long javaCalls=0;
        try{
            Stage(directory,"loading source image");
            image=NativeLibrary.Load(dll);bool fixture=String.IsNullOrEmpty(platformName);
            IntPtr source=NativeLibrary.GetExport(image,"boom_java_string_literal_pool"),ctx=Memory(memory,32),args=Memory(memory,16),caller=Memory(memory,32),regions=Memory(memory,64);
            IntPtr descriptors=NativeLibrary.GetExport(image,"boom_batch_type_descriptors"),arrayType=Marshal.ReadIntPtr(descriptors,d.Array*8),platform,vm,roots,strings;
            int rootCount;
            if(fixture){
                roots=Memory(memory,8+d.Text.Length*16);rootCount=1+d.Text.Length*2;strings=Memory(memory,80);
                IntPtr entries=Memory(memory,d.Text.Length*16),states=Memory(memory,d.Text.Length*4);
                Marshal.WriteInt32(strings,0,0x4a534c50);Marshal.WriteInt32(strings,4,1);Marshal.WriteInt32(strings,8,d.Text.Length);Marshal.WriteInt32(strings,12,1);
                Marshal.WriteIntPtr(strings,16,entries);Marshal.WriteIntPtr(strings,24,IntPtr.Add(roots,8));Marshal.WriteIntPtr(strings,32,states);Marshal.WriteIntPtr(strings,40,Marshal.ReadIntPtr(source,40));
                for(int i=0;i<4;i++)Marshal.WriteInt32(strings,48+i*4,Marshal.ReadInt32(source,48+i*4));
                for(int i=0;i<d.Text.Length;i++){
                    string text=d.Text[i];IntPtr chars=Memory(memory,Math.Max(2,text.Length*2));uint hash=0;
                    for(int j=0;j<text.Length;j++){Marshal.WriteInt16(chars,j*2,unchecked((short)text[j]));hash=unchecked(hash*31+text[j]);}
                    Marshal.WriteIntPtr(entries,i*16,chars);Marshal.WriteInt32(entries,i*16+8,text.Length);Marshal.WriteInt32(entries,i*16+12,unchecked((int)hash));
                }
                platform=Memory(memory,112);vm=Memory(memory,112);IntPtr heapCell=Marshal.ReadIntPtr(NativeLibrary.GetExport(image,"boom_java_class_pool"),48);
                foreach(IntPtr p in new[]{platform,vm}){
                    Marshal.WriteInt32(p,4,2);Marshal.WriteIntPtr(p,16,heapCell);Marshal.WriteIntPtr(p,24,strings);Marshal.WriteIntPtr(p,32,arrayType);
                    Marshal.WriteIntPtr(p,80,NativeLibrary.GetExport(lib,"boom_java_property_array"));Marshal.WriteIntPtr(p,88,NativeLibrary.GetExport(lib,"boom_java_property_copy"));
                    Marshal.WriteIntPtr(p,96,NativeLibrary.GetExport(lib,"boom_java_property_literal"));Marshal.WriteIntPtr(p,104,NativeLibrary.GetExport(image,"boom_java_string_literal"));
                }
                IntPtr rows=Memory(memory,39*16),fallback=Memory(memory,d.Fallbacks.Length*4),pairs=Memory(memory,d.Pairs.Length*8);
                for(int i=0;i<39;i++)for(int j=0;j<3;j++)Marshal.WriteInt32(rows,i*16+j*4,d.Rows[i][j]);
                for(int i=0;i<d.Fallbacks.Length;i++)Marshal.WriteInt32(fallback,i*4,d.Fallbacks[i]);
                for(int i=0;i<d.Pairs.Length;i++)for(int j=0;j<2;j++)Marshal.WriteInt32(pairs,i*8+j*4,d.Pairs[i][j]);
                Marshal.WriteInt32(platform,0,0x50524f50);Marshal.WriteIntPtr(platform,40,roots);Marshal.WriteIntPtr(platform,48,rows);Marshal.WriteInt32(platform,56,39);Marshal.WriteIntPtr(platform,64,fallback);
                Marshal.WriteInt32(vm,0,0x564d5052);Marshal.WriteInt32(vm,8,d.Pairs.Length);Marshal.WriteIntPtr(vm,40,pairs);
            }else{
                platform=NativeLibrary.GetExport(image,"boom_java_platform_properties_pool");vm=NativeLibrary.GetExport(image,"boom_java_vm_properties_pool");
                roots=NativeLibrary.GetExport(image,"boom_java_properties_roots");rootCount=checked((int)Marshal.ReadInt64(NativeLibrary.GetExport(image,"boom_java_properties_root_count")));
                strings=NativeLibrary.GetExport(image,"boom_java_properties_string_pool");
            }
            Entry platformEntry=fixture?null:Fn<Entry>(image,platformName),vmEntry=fixture?null:Fn<Entry>(image,vmName);
            Stage(directory,"source property pools prepared");
            var rawPlatform=Fn<Native>(lib,"boom_platform_properties");var rawVm=Fn<Native>(lib,"boom_vm_properties");var allocate=Fn<Alloc>(lib,"boom_heap_alloc");
            var make=Fn<Make>(lib,"boom_object_new");var collect=Fn<Collect>(lib,"boom_heap_collect_spans");var copy=Fn<Copy>(lib,"boom_java_property_copy");
            IntPtr statics=NativeLibrary.GetExport(image,"boom_probe_static_roots");long staticCount=Marshal.ReadInt64(NativeLibrary.GetExport(image,"boom_probe_static_root_count"));
            heap=Fn<Create>(lib,"boom_heap_create")(16*1024*1024);Need(heap!=IntPtr.Zero&&Fn<Bind>(image,"boom_java_string_literals_bind_heap")(heap)==1,"Property heap bind failed");
            Stage(directory,"heap bound");long filled=Fill(allocate,heap);Stage(directory,"calling cold OOM native envelope");Reset(ctx);IntPtr failed=platformEntry==null?rawPlatform(ctx,args,platform):platformEntry(ctx,args);
            Need(failed==IntPtr.Zero&&Marshal.ReadInt32(ctx)==3&&Marshal.ReadInt32(platform,8)==0&&Marshal.ReadInt32(platform,12)==0&&Marshal.ReadIntPtr(roots)==IntPtr.Zero,"Cold property OOM published a fake snapshot");
            Stage(directory,"collecting cold OOM garbage");long collected=GC(collect,heap,regions,roots,rootCount,source,statics,staticCount,caller);Need(collected>=filled,"Cold OOM garbage was retained");
            // Cold concurrent publication: each caller gets its own array.
            Stage(directory,"cold concurrent publication");IntPtr[] first=new IntPtr[8];Parallel.For(0,8,worker=>{
                IntPtr c=Marshal.AllocHGlobal(32);try{first[worker]=Call(rawPlatform,platformEntry,c,IntPtr.Zero,platform);}finally{Marshal.FreeHGlobal(c);}
            });
            IntPtr snapshot=Marshal.ReadIntPtr(roots);Array(snapshot,arrayType,39);Need(Marshal.ReadInt32(platform,8)==2,"Property snapshot was not published");
            var distinct=new HashSet<IntPtr>();foreach(IntPtr a in first){Array(a,arrayType,39);Need(a!=snapshot&&distinct.Add(a),"Property calls shared a mutable array");}
            for(int i=0;i<39;i++){
                string actual=Text(Marshal.ReadIntPtr(first[0],i*8),strings);
                Need(actual==expected[i],"Native/JVM platform property differs at "+d.Names[i]);
                for(int j=1;j<first.Length;j++)Need(Marshal.ReadIntPtr(first[j],i*8)==Marshal.ReadIntPtr(snapshot,i*8),"Concurrent snapshot values differ");
            }
            Marshal.WriteIntPtr(first[0],0,IntPtr.Zero);IntPtr fresh=Call(rawPlatform,platformEntry,ctx,args,platform);
            Need(Marshal.ReadIntPtr(fresh)==Marshal.ReadIntPtr(snapshot),"Caller mutated the cached property snapshot");
            if(!fixture){
                Stage(directory,"checking original class preparation");
                Need(Marshal.ReadInt32(NativeLibrary.GetExport(image,"boom_class"+d.Raw),8)==2,"Raw Java class preparation not executed");
                for(int i=0;i<39;i++)Need(Marshal.ReadInt32(NativeLibrary.GetExport(image,"boom_s"+d.Raw+"_"+d.Rows[i][3]))==i,"Raw original ConstantValue preparation differs");
                IntPtr map=NativeLibrary.GetExport(image,"boom_runtime_type_map"),rows=Marshal.ReadIntPtr(map,16),layout=IntPtr.Zero;
                for(int i=0;i<Marshal.ReadInt32(map,8);i++)if(Marshal.ReadInt32(rows,i*40+16)==d.Raw&&Marshal.ReadInt32(rows,i*40+20)==0)layout=Marshal.ReadIntPtr(rows,i*40);
                Reset(ctx);IntPtr raw=make(heap,layout,ctx);Need(raw!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Normal Raw allocation failed");Marshal.WriteIntPtr(caller,raw);Marshal.WriteIntPtr(args,raw);
                Stage(directory,"calling original Raw constructor");Reset(ctx);Fn<Entry>(image,ctorName)(ctx,args);javaCalls++;Need(Marshal.ReadInt32(ctx)==0,"Original Raw constructor failed");
                IntPtr captured=Marshal.ReadIntPtr(raw,d.FieldOffset);Array(captured,arrayType,39);Need(captured!=snapshot,"Original constructor stored the private snapshot");
                Stage(directory,"calling original propDefault");var getter=Fn<Entry>(image,getterName);
                for(int i=0;i<39;i++){Reset(ctx);Marshal.WriteInt64(args,8,i);IntPtr got=getter(ctx,args);javaCalls++;Need(Marshal.ReadInt32(ctx)==0&&Text(got,strings)==expected[i],"Original propDefault/aaload differs");}
                Stage(directory,"original getters complete; calling bounds path");Reset(ctx);Marshal.WriteInt64(args,8,-1);Need(getter(ctx,args)==IntPtr.Zero&&Marshal.ReadInt32(ctx)!=0,"Original getter lost bounds exception");javaCalls++;
                Stage(directory,"original getter bounds path complete");
            }
            Stage(directory,"calling VM native envelope");IntPtr values=Call(rawVm,vmEntry,ctx,args,vm);Array(values,arrayType,d.Pairs.Length*2+1);Marshal.WriteIntPtr(caller,8,values);
            for(int i=0;i<d.Pairs.Length;i++)for(int j=0;j<2;j++)Need(Text(Marshal.ReadIntPtr(values,(i*2+j)*8),strings)==d.Text[d.Pairs[i][j]],"Native VM profile value differs");
            Need(Marshal.ReadIntPtr(values,d.Pairs.Length*16)==IntPtr.Zero,"VM property terminator differs");
            Marshal.WriteIntPtr(values,0,IntPtr.Zero);IntPtr next=Call(rawVm,vmEntry,ctx,args,vm);Need(next!=values&&Text(Marshal.ReadIntPtr(next),strings)==d.Text[d.Pairs[0][0]],"VM arrays are not independent");
            Stage(directory,"warm parallel arrays");const int workers=8,iterations=512;Parallel.For(0,workers,worker=>{
                IntPtr c=Marshal.AllocHGlobal(32);try{for(int j=0;j<iterations;j++){
                    IntPtr a=Call(rawPlatform,platformEntry,c,IntPtr.Zero,platform),b=Call(rawVm,vmEntry,c,IntPtr.Zero,vm);Array(a,arrayType,39);Array(b,arrayType,d.Pairs.Length*2+1);
                    Need(Marshal.ReadIntPtr(a)==Marshal.ReadIntPtr(snapshot)&&Text(Marshal.ReadIntPtr(b),strings)==d.Text[d.Pairs[0][0]],"Parallel property values differ");
                }}finally{Marshal.FreeHGlobal(c);}
            });
            Stage(directory,"normal UTF16 copy");int copied=0;foreach(string sample in new[]{"", "Latin\u00ff", "\u4e2d\ud83d\ude00", "nul\0\ud800x\udc00"}){
                IntPtr chars=Memory(memory,Math.Max(2,sample.Length*2));for(int i=0;i<sample.Length;i++)Marshal.WriteInt16(chars,i*2,unchecked((short)sample[i]));
                Reset(ctx);IntPtr p=copy(ctx,platform,chars,(uint)sample.Length);Need(p!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0&&Text(p,strings)==sample,"Normal property copy lost UTF16 data");copied++;
            }
            Stage(directory,"error guards");int guards=0;IntPtr bad=Memory(memory,112);byte[] poolBytes=new byte[112];Marshal.Copy(platform,poolBytes,0,112);Marshal.Copy(poolBytes,0,bad,112);
            Reset(ctx);Marshal.WriteInt32(ctx,99);Need(rawPlatform(ctx,args,platform)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==99&&Marshal.ReadInt32(ctx,4)==37,"Property service replaced pending exception");guards++;
            Reset(ctx);Marshal.WriteInt32(bad,4,9);Need(rawPlatform(ctx,args,bad)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7,"Invalid platform ABI accepted");guards++;
            Reset(ctx);Marshal.WriteInt32(bad,4,2);Marshal.WriteInt32(bad,56,129);Need(rawPlatform(ctx,args,bad)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7,"Invalid platform count accepted");guards++;
            Reset(ctx);Need(Fn<NewArray>(lib,"boom_java_property_array")(ctx,platform,-1)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==2,"Negative source array size accepted");guards++;
            Reset(ctx);Need(copy(ctx,platform,IntPtr.Zero,1)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7,"Null nonempty native string buffer accepted");guards++;
            var materialize=Fn<Materialize>(lib,"boom_exception_materialize");
            Reset(ctx);Marshal.WriteInt32(ctx,5);Need(materialize(ctx)==1&&Marshal.ReadInt32(ctx)==5&&Marshal.ReadInt32(ctx,4)==37&&Marshal.ReadInt32(ctx,8)==73&&Marshal.ReadIntPtr(ctx,16)==IntPtr.Zero,"Unbound materializer changed a pending source error");guards++;
            Need(materialize(IntPtr.Zero)==1,"Null materialization context accepted");guards++;
            IntPtr badException=Memory(memory,160);Reset(ctx);Marshal.WriteInt32(ctx,5);Marshal.WriteIntPtr(ctx,24,badException);
            Need(materialize(ctx)==1&&Marshal.ReadInt32(ctx)==5&&Marshal.ReadIntPtr(ctx,16)==IntPtr.Zero,"Incompatible exception-pool metadata was used");guards++;
            Marshal.Copy(vm,poolBytes,0,112);Marshal.Copy(poolBytes,0,bad,112);Reset(ctx);Marshal.WriteInt32(bad,8,0);Need(rawVm(ctx,args,bad)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7,"Empty invalid VM profile accepted");guards++;
            // Exhaustion after publication must preserve the snapshot and its roots.
            Stage(directory,"warm OOM");filled=Fill(allocate,heap);Reset(ctx);failed=platformEntry==null?rawPlatform(ctx,args,platform):platformEntry(ctx,args);
            Need(failed==IntPtr.Zero&&Marshal.ReadInt32(ctx)==3&&Marshal.ReadIntPtr(roots)==snapshot&&Marshal.ReadInt32(platform,8)==2,"Clone OOM damaged a published snapshot");guards++;
            Reset(ctx);Need((vmEntry==null?rawVm(ctx,args,vm):vmEntry(ctx,args))==IntPtr.Zero&&Marshal.ReadInt32(ctx)==3,"VM OOM returned a fake empty array");guards++;
            Stage(directory,"collecting warm source graph");long garbage=GC(collect,heap,regions,roots,rootCount,source,statics,staticCount,caller);Need(garbage>=filled,"Warm property garbage was retained");
            fresh=Call(rawPlatform,platformEntry,ctx,args,platform);next=Call(rawVm,vmEntry,ctx,args,vm);
            for(int i=0;i<39;i++)Need(Text(Marshal.ReadIntPtr(fresh,i*8),strings)==expected[i],"Collected snapshot changed");
            var result=new long[]{39,d.Pairs.Length,8+workers*iterations*2,javaCalls,guards,copied,collected,garbage,rootCount,Marshal.ReadInt64(heap,56)};
            Need(destroy(heap)==1,"Property heap destroy failed");heap=IntPtr.Zero;return result;
        }finally{
            if(heap!=IntPtr.Zero)destroy(heap);
            for(int i=memory.Count-1;i>=0;i--)Marshal.FreeHGlobal(memory[i]);if(image!=IntPtr.Zero)NativeLibrary.Free(image);NativeLibrary.Free(lib);
        }
    }
}
