using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;

// Development host: prepares normal source-shaped Strings, never their Java
// constructors. Canonicalization, table growth and collection execute MASM.
public static class BoomJavaStringInternProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Make(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ArrayNew(IntPtr heap,int count,uint kind,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Intern(IntPtr ctx,IntPtr args,IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Literal(IntPtr ctx,IntPtr pool,uint index);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ClassLoad(IntPtr ctx,IntPtr pool,uint type);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(IntPtr ctx,IntPtr args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Collect(IntPtr heap,IntPtr regions,ulong count);
    sealed class Case {public int Kind,Index,Type;public char[] Units;}
    static T Fn<T>(IntPtr m,string n) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(m,n));}
    static void Need(bool b,string m){if(!b)throw new Exception(m);}
    static void Reset(IntPtr p){for(int i=0;i<32;i+=8)Marshal.WriteInt64(p,i,0);Marshal.WriteInt32(p,4,37);Marshal.WriteInt32(p,8,73);}
    static IntPtr Context(){IntPtr p=Marshal.AllocHGlobal(32);Reset(p);return p;}
    static IntPtr MakeString(IntPtr heap,IntPtr layout,IntPtr pool,char[] chars,bool wide,IntPtr ctx,Make make,ArrayNew array){
        if(!wide)foreach(char c in chars)if(c>255){wide=true;break;}
        Reset(ctx);IntPtr bytes=array(heap,checked(chars.Length*(wide?2:1)),8,ctx);Need(bytes!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"String value allocation failed");
        for(int i=0;i<chars.Length;i++){if(wide)Marshal.WriteInt16(bytes,i*2,unchecked((short)chars[i]));else Marshal.WriteByte(bytes,i,(byte)chars[i]);}
        IntPtr value=make(heap,layout,ctx);Need(value!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"String allocation failed");
        Marshal.WriteIntPtr(value,bytes);Marshal.WriteByte(value,Marshal.ReadInt32(pool,44),(byte)(wide?1:0));return value;
    }
    static IntPtr Call(Intern raw,Entry entry,IntPtr ctx,IntPtr args,IntPtr pool,IntPtr value){Reset(ctx);Marshal.WriteIntPtr(args,value);IntPtr r=entry==null?raw(ctx,args,pool):new IntPtr(unchecked((long)entry(ctx,args)));Need(r!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Intern returned error kind "+Marshal.ReadInt32(ctx));return r;}
    static long GC(Collect collect,IntPtr heap,IntPtr memory,IntPtr literal,IntPtr classes,IntPtr names,IntPtr root,IntPtr caller){
        IntPtr[] pointers={Marshal.ReadIntPtr(literal,24),Marshal.ReadIntPtr(classes,16),names,root,caller};
        long[] counts={Marshal.ReadInt32(literal,8)*2L,Marshal.ReadInt64(NativeLibrary.GetExport(imageForRoots,"boom_java_class_root_count")),Marshal.ReadInt64(NativeLibrary.GetExport(imageForRoots,"boom_java_class_name_root_count")),1,1};
        for(int i=0;i<pointers.Length;i++){Marshal.WriteIntPtr(memory,i*16,pointers[i]);Marshal.WriteInt64(memory,i*16+8,counts[i]);}
        long result=collect(heap,memory,5);Need(result>=0,"Intern root-region collection failed");return result;
    }
    [ThreadStatic] static IntPtr imageForRoots;
    public static long[] Run(string runtime,string dll,string directory,string internName,string getNameName){
        IntPtr lib=NativeLibrary.Load(runtime),image=IntPtr.Zero,heap=IntPtr.Zero,ctx=IntPtr.Zero,args=IntPtr.Zero,poolMemory=IntPtr.Zero,rootMemory=IntPtr.Zero,regions=IntPtr.Zero;
        var destroy=Fn<Destroy>(lib,"boom_heap_destroy");
        try{
            image=NativeLibrary.Load(dll);imageForRoots=image;ctx=Context();args=Marshal.AllocHGlobal(16);regions=Marshal.AllocHGlobal(80);
            IntPtr literals=NativeLibrary.GetExport(image,"boom_java_string_literal_pool"),classes=NativeLibrary.GetExport(image,"boom_java_class_pool"),names=NativeLibrary.GetExport(image,"boom_java_class_name_pool");
            IntPtr nameRoots=NativeLibrary.GetExport(image,"boom_java_class_name_roots"),layout=Marshal.ReadIntPtr(literals,40),pool,root;
            bool fixture=String.IsNullOrEmpty(internName);
            if(fixture){
                poolMemory=Marshal.AllocHGlobal(96);rootMemory=Marshal.AllocHGlobal(8);for(int i=0;i<96;i+=8)Marshal.WriteInt64(poolMemory,i,0);Marshal.WriteInt64(rootMemory,0);
                pool=poolMemory;root=rootMemory;Marshal.WriteInt32(pool,0,0x4a494e50);Marshal.WriteInt32(pool,4,1);
                // The Class pool holds an address of the heap cell, not a heap.
                Marshal.WriteIntPtr(pool,24,Marshal.ReadIntPtr(classes,48));Marshal.WriteIntPtr(pool,32,layout);
                for(int i=0;i<4;i++)Marshal.WriteInt32(pool,40+i*4,Marshal.ReadInt32(literals,48+i*4));
                Marshal.WriteIntPtr(pool,56,literals);Marshal.WriteIntPtr(pool,64,names);Marshal.WriteIntPtr(pool,72,root);Marshal.WriteInt32(pool,80,32);Marshal.WriteInt32(pool,84,1);
            }else{pool=NativeLibrary.GetExport(image,"boom_java_string_intern_pool");root=NativeLibrary.GetExport(image,"boom_java_string_intern_root");}
            var raw=Fn<Intern>(lib,"boom_java_string_intern");Entry entry=fixture?null:Fn<Entry>(image,internName),getName=Fn<Entry>(image,getNameName);
            var make=Fn<Make>(lib,"boom_object_new");var array=Fn<ArrayNew>(lib,"boom_array_new");var literal=Fn<Literal>(image,"boom_java_string_literal");var load=Fn<ClassLoad>(lib,"boom_java_class_load");var collect=Fn<Collect>(lib,"boom_heap_collect_spans");
            heap=Fn<Create>(lib,"boom_heap_create")(192*1024*1024);Need(heap!=IntPtr.Zero&&Fn<Bind>(image,"boom_java_string_literals_bind_heap")(heap)==1,"Intern heap bind failed");
            var cases=new List<Case>();using(var f=new BinaryReader(File.OpenRead(Path.Combine(directory,"static-cases.bin")))){Need(f.ReadUInt32()==0x4a494e54,"Invalid static intern fixture");int n=f.ReadInt32();for(int i=0;i<n;i++){var c=new Case{Kind=f.ReadInt32(),Index=f.ReadInt32(),Type=f.ReadInt32()};c.Units=new char[f.ReadInt32()];for(int j=0;j<c.Units.Length;j++)c.Units[j]=(char)f.ReadUInt16();cases.Add(c);}Need(f.BaseStream.Position==f.BaseStream.Length,"Trailing static intern cases");}
            long staticCalls=0;Case ldcRace=null,nameRace=null;
            for(int i=0;i<cases.Count;i++){
                Case c=cases[i];if(c.Kind==0&&ldcRace==null){ldcRace=c;continue;}if(c.Kind==1&&nameRace==null){nameRace=c;continue;}
                IntPtr targetPool=c.Kind==0?literals:Marshal.ReadIntPtr(names,24);Need(Marshal.ReadIntPtr(Marshal.ReadIntPtr(targetPool,24),c.Index*16)==IntPtr.Zero,"Static String was resolved before adoption test");
                IntPtr value=MakeString(heap,layout,pool,c.Units,(i&1)!=0,ctx,make,array);long before=Marshal.ReadInt64(heap,48);
                Need(Call(raw,entry,ctx,args,pool,value)==value&&Marshal.ReadInt64(heap,48)==before,"Intern-before-static did not adopt caller without allocation");
                if(c.Kind==0){Reset(ctx);Need(literal(ctx,literals,(uint)c.Index)==value&&Marshal.ReadInt32(ctx)==0,"ldc did not reuse adopted String");}
                else{Reset(ctx);IntPtr mirror=load(ctx,classes,(uint)c.Type);Need(mirror!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Early java.base mirror failed");Marshal.WriteIntPtr(args,mirror);Need(getName(ctx,args)==unchecked((ulong)value.ToInt64())&&Marshal.ReadInt32(ctx)==0,"Class.getName did not reuse adopted String");}
                IntPtr duplicate=MakeString(heap,layout,pool,c.Units,(i&1)==0,ctx,make,array);Need(Call(raw,entry,ctx,args,pool,duplicate)==value,"Static cross-coder canonical identity differs");staticCalls+=2;
            }
            const int workers=8;long races=0;
            foreach(Case c in new[]{ldcRace,nameRace}){
                Need(c!=null,"Missing static race fixture");var inputs=new IntPtr[workers];var outputs=new IntPtr[workers];IntPtr mirror=IntPtr.Zero;
                for(int i=0;i<workers;i++)inputs[i]=MakeString(heap,layout,pool,c.Units,(i&1)!=0,ctx,make,array);
                if(c.Kind==1){Reset(ctx);mirror=load(ctx,classes,(uint)c.Type);Need(mirror!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Name race mirror failed");}
                Parallel.For(0,workers,i=>{IntPtr x=Context(),a=Marshal.AllocHGlobal(16);try{if((i&1)==0)outputs[i]=Call(raw,entry,x,a,pool,inputs[i]);else if(c.Kind==0)outputs[i]=literal(x,literals,(uint)c.Index);else{Marshal.WriteIntPtr(a,mirror);outputs[i]=new IntPtr(unchecked((long)getName(x,a)));}Need(outputs[i]!=IntPtr.Zero&&Marshal.ReadInt32(x)==0,"Concurrent static interning failed");}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(x);}});
                foreach(IntPtr p in outputs)Need(p==outputs[0],"Concurrent static producers published different identities");races+=workers;
            }
            var canonical=new List<IntPtr>();var dynamicInputs=new List<char[]>();
            string prefix="BoomNativeIntern_96_7fd34e_";
            for(int i=0;i<8192;i++)dynamicInputs.Add((prefix+i.ToString("x8")).ToCharArray());
            dynamicInputs.Add((prefix+"Aa").ToCharArray());dynamicInputs.Add((prefix+"BB").ToCharArray());dynamicInputs.Add(new[]{'Z','\0','\u00ff','\u4e2d','\ud800','q','\udc00','\ud83d','\ude00'});
            dynamicInputs.Add(new string('x',70001).ToCharArray());
            foreach(char[] text in dynamicInputs){IntPtr value=MakeString(heap,layout,pool,text,false,ctx,make,array);Need(Call(raw,entry,ctx,args,pool,value)==value,"Fresh dynamic intern did not return caller");IntPtr other=MakeString(heap,layout,pool,text,true,ctx,make,array);Need(Call(raw,entry,ctx,args,pool,other)==value,"Dynamic equality/hash collision/coder differs");canonical.Add(value);}
            Need(canonical[8192]!=canonical[8193],"Equal hashes merged different UTF16 strings");
            char[] shared=(prefix+"shared_cold").ToCharArray();var sharedInput=new IntPtr[workers];var sharedOutput=new IntPtr[workers];for(int i=0;i<workers;i++)sharedInput[i]=MakeString(heap,layout,pool,shared,(i&1)!=0,ctx,make,array);
            Parallel.For(0,workers,i=>{IntPtr x=Context(),a=Marshal.AllocHGlobal(16);try{for(int n=0;n<1024;n++)sharedOutput[i]=Call(raw,entry,x,a,pool,sharedInput[i]);}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(x);}});
            foreach(IntPtr p in sharedOutput)Need(p==sharedOutput[0],"Concurrent dynamic interning diverged");canonical.Add(sharedOutput[0]);
            Need(Array.IndexOf(sharedInput,sharedOutput[0])>=0,"Intern allocated a replacement canonical String");
            long oracleCases=0;string oraclePath=Path.Combine(directory,"oracle.tsv");
            if(File.Exists(oraclePath)){
                IntPtr table=Marshal.ReadIntPtr(root);int capacity=Marshal.ReadInt32(pool,16);var hashes=new Dictionary<IntPtr,uint>();
                for(int i=0;i<capacity;i++){IntPtr p=Marshal.ReadIntPtr(table,i*8);if(p!=IntPtr.Zero)hashes.Add(p,unchecked((uint)Marshal.ReadInt32(table,capacity*8+i*4)));}
                foreach(string line in File.ReadLines(oraclePath)){string[] fields=line.Split('\t');int id=int.Parse(fields[0]);Need(id==oracleCases&&id<dynamicInputs.Count&&fields[2]=="1"&&fields[3]=="1"&&hashes[canonical[id]]==uint.Parse(fields[1]),"Normal String intern/hash differs from JVM: "+id);oracleCases++;}
                Need(oracleCases==dynamicInputs.Count,"Incomplete JVM intern comparison");
            }
            int errors=0;Reset(ctx);Need(raw(ctx,IntPtr.Zero,pool)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7,"Null argv accepted");errors++;
            Reset(ctx);Marshal.WriteIntPtr(args,IntPtr.Zero);Need(raw(ctx,args,pool)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==4,"Null String accepted");errors++;
            Reset(ctx);Marshal.WriteInt32(ctx,16);Marshal.WriteIntPtr(ctx,16,canonical[0]);Marshal.WriteIntPtr(args,canonical[1]);Need(raw(ctx,args,pool)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==16&&Marshal.ReadIntPtr(ctx,16)==canonical[0]&&Marshal.ReadInt32(ctx,4)==37&&Marshal.ReadInt32(ctx,8)==73,"Intern consumed pending exception context");errors++;
            Reset(ctx);IntPtr broken=make(heap,layout,ctx);Marshal.WriteIntPtr(args,broken);Need(raw(ctx,args,pool)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7,"Uninitialized String value accepted");errors++;
            IntPtr badCoder=MakeString(heap,layout,pool,new[]{'a'},false,ctx,make,array);Marshal.WriteByte(badCoder,Marshal.ReadInt32(pool,44),2);Reset(ctx);Marshal.WriteIntPtr(args,badCoder);Need(raw(ctx,args,pool)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7,"Invalid coder accepted");errors++;
            IntPtr odd=MakeString(heap,layout,pool,new[]{'a','b','c'},false,ctx,make,array);Marshal.WriteByte(odd,Marshal.ReadInt32(pool,44),1);Reset(ctx);Marshal.WriteIntPtr(args,odd);Need(raw(ctx,args,pool)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7,"Odd UTF16 byte length accepted");errors++;
            IntPtr foreign=Fn<Create>(lib,"boom_heap_create")(65536);Need(foreign!=IntPtr.Zero,"Foreign heap fixture failed");try{IntPtr text=MakeString(foreign,layout,pool,new[]{'x'},false,ctx,make,array);Reset(ctx);Marshal.WriteIntPtr(args,text);Need(raw(ctx,args,pool)==IntPtr.Zero&&Marshal.ReadInt32(ctx)==7,"Foreign heap String accepted");errors++;}finally{destroy(foreign);}
            int cap=Marshal.ReadInt32(pool,16);Need(cap>=16384&&Marshal.ReadInt32(pool,12)==canonical.Count,"Dynamic table growth/count differs");
            for(int i=canonical.Count;i<cap*3/4;i++){IntPtr value=MakeString(heap,layout,pool,(prefix+"fill_"+i).ToCharArray(),false,ctx,make,array);Need(Call(raw,entry,ctx,args,pool,value)==value,"Fill intern failed");canonical.Add(value);}
            IntPtr retry=MakeString(heap,layout,pool,(prefix+"oom_retry").ToCharArray(),false,ctx,make,array),oldTable=Marshal.ReadIntPtr(root);
            int filler=0;for(int size=65536;size>=32;size/=2)for(;;){Reset(ctx);if(array(heap,size,8,ctx)==IntPtr.Zero)break;filler++;}
            Need(filler>0,"OOM fixture did not consume heap");Reset(ctx);Marshal.WriteIntPtr(args,retry);Need((entry==null?raw(ctx,args,pool):new IntPtr(unchecked((long)entry(ctx,args))))==IntPtr.Zero&&Marshal.ReadInt32(ctx)==3&&Marshal.ReadIntPtr(root)==oldTable&&Marshal.ReadInt32(pool,16)==cap&&Marshal.ReadInt32(pool,8)==0,"Failed intern growth published table/held lock");errors++;
            Need(Call(raw,entry,ctx,args,pool,canonical[0])==canonical[0],"Existing intern failed under OOM");
            Marshal.WriteIntPtr(args,retry);long freed=GC(collect,heap,regions,literals,classes,nameRoots,root,args);
            Need(freed>0&&Call(raw,entry,ctx,args,pool,retry)==retry&&Marshal.ReadInt32(pool,16)==cap*2,"Intern failed to recover after explicit collection");
            Marshal.WriteIntPtr(args,retry);freed+=GC(collect,heap,regions,literals,classes,nameRoots,root,args);
            long warm=Marshal.ReadInt64(heap,48);foreach(IntPtr p in canonical)Need(Call(raw,entry,ctx,args,pool,p)==p,"Canonical dynamic String lost after collection");Need(Marshal.ReadInt64(heap,48)==warm,"Warm intern allocated after collection");
            return new long[]{staticCalls,races,dynamicInputs.Count,workers*1024,errors,cap*2,freed,canonical.Count,Marshal.ReadInt64(heap,56),oracleCases};
        }finally{imageForRoots=IntPtr.Zero;if(regions!=IntPtr.Zero)Marshal.FreeHGlobal(regions);if(poolMemory!=IntPtr.Zero)Marshal.FreeHGlobal(poolMemory);if(rootMemory!=IntPtr.Zero)Marshal.FreeHGlobal(rootMemory);if(args!=IntPtr.Zero)Marshal.FreeHGlobal(args);if(ctx!=IntPtr.Zero)Marshal.FreeHGlobal(ctx);if(heap!=IntPtr.Zero)destroy(heap);if(image!=IntPtr.Zero)NativeLibrary.Free(image);NativeLibrary.Free(lib);}
    }
}
