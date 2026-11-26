using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

// Development FFI driver only. Name resolution and Java execution are MASM.
public static class BoomNormalClassLookupProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int ReleaseFrames();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr cls,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr New(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr heap,ulong bytes,ulong refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Lookup(IntPtr ctx,IntPtr args,IntPtr pool,int op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(IntPtr ctx,IntPtr args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint TypeId(IntPtr ctx,IntPtr pool,IntPtr mirror);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int BindModule(IntPtr pool,uint id,IntPtr module,IntPtr ctx);
    static T Fn<T>(IntPtr m,string n) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(m,n));}
    static void Need(bool x,string m){if(!x)throw new Exception(m);}
    static void ReleaseTrace(IntPtr dll){IntPtr p;if(NativeLibrary.TryGetExport(dll,"boom_release_trace_pool",out p))Need(Marshal.GetDelegateForFunctionPointer<ReleaseFrames>(p)()==0,"Source image still owns active Java frames");}
    static IntPtr Memory(List<IntPtr> owned,int bytes){IntPtr p=Marshal.AllocHGlobal(bytes);for(int i=0;i<bytes;i++)Marshal.WriteByte(p,i,0);owned.Add(p);return p;}
    static void Reset(IntPtr p){for(int i=0;i<32;i+=8)Marshal.WriteInt64(p,i,0);}
    static uint Hash(string s){uint h=0;foreach(char c in s)h=unchecked(h*31+c);return h;}
    static string HexName(string s){var chars=new char[s.Length/4];for(int i=0;i<chars.Length;i++)chars[i]=(char)Convert.ToUInt16(s.Substring(i*4,4),16);return new string(chars);}
    static string Text(IntPtr sp,IntPtr s){Need(s!=IntPtr.Zero,"Missing enum name");IntPtr a=Marshal.ReadIntPtr(s,Marshal.ReadInt32(sp,48));int coder=Marshal.ReadByte(s,Marshal.ReadInt32(sp,52)),n=checked((int)Marshal.ReadInt64(a,-16))>>coder;var text=new char[n];for(int i=0;i<n;i++)text[i]=(char)(coder==0?Marshal.ReadByte(a,i):(ushort)Marshal.ReadInt16(a,2*i));return new string(text);}
    public static long[] Run(string runtime,string image,string nameFile,string oracleFile,string enumFile,string nativeName,string bootstrapName,
        string publicName,string enumName,string enumOrdinal,string stopName,bool stopOnly){
        IntPtr lib=NativeLibrary.Load(runtime),dll=IntPtr.Zero,heap=IntPtr.Zero;var owned=new List<IntPtr>();var destroy=Fn<Destroy>(lib,"boom_heap_destroy");
        try{
            dll=NativeLibrary.Load(image);heap=Fn<Create>(lib,"boom_heap_create")(128UL*1024*1024);Need(heap!=IntPtr.Zero&&Fn<Bind>(dll,"boom_java_string_literals_bind_heap")(heap)==1,"Lookup source heap bind failed");
            IntPtr ctx=Memory(owned,32),args=Memory(owned,32),cp=NativeLibrary.GetExport(dll,"boom_java_class_pool"),sp=NativeLibrary.GetExport(dll,"boom_java_string_literal_pool"),pool=NativeLibrary.GetExport(dll,"boom_java_class_lookup_pool"),diagnostic=NativeLibrary.GetExport(dll,"boom_diagnostic_pool");
            var create=Fn<New>(lib,"boom_object_new");var alloc=Fn<Alloc>(lib,"boom_heap_alloc");var lookup=Fn<Entry>(dll,nativeName);var boot=Fn<Entry>(dll,bootstrapName+"_native");var java=Fn<Entry>(dll,publicName);var typeid=Fn<TypeId>(lib,"boom_java_class_typeid");var kernel=Fn<Lookup>(lib,"boom_java_class_lookup");
            int classId=Marshal.ReadInt32(cp,108);Need(Marshal.ReadInt32(NativeLibrary.GetExport(dll,"boom_class"+classId),8)==0,"Lookup source Class was preinitialized");
            const int workers=8;IntPtr cold=String(heap,sp,ctx,"java.lang.Object",create,alloc);var mirrors=new ulong[workers];
            using(var gate=new Barrier(workers))Parallel.For(0,workers,w=>{IntPtr c=Marshal.AllocHGlobal(32),a=Marshal.AllocHGlobal(32);try{Reset(c);for(int i=0;i<32;i+=8)Marshal.WriteInt64(a,i,0);Marshal.WriteIntPtr(a,cold);gate.SignalAndWait();mirrors[w]=lookup(c,a);Need(mirrors[w]!=0&&Marshal.ReadInt32(c)==0,"Cold source Class/lookup failed");}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});
            foreach(ulong m in mirrors)Need(m==mirrors[0],"Cold canonical Class publication differs");
            if(stopOnly){Marshal.WriteIntPtr(args,String(heap,sp,ctx,stopName,create,alloc));Marshal.WriteInt64(args,8,1);Reset(ctx);ulong value=lookup(ctx,args);Need(value==0&&Marshal.ReadInt32(ctx)==0xB001&&Marshal.ReadInt32(diagnostic,8)==2,"Unselected source initializer did not stop");return new long[]{Marshal.ReadInt32(ctx),Marshal.ReadInt32(diagnostic,32),Marshal.ReadInt32(diagnostic,8),workers};}
            // The module bootstrap is a separate unimplemented game phase.
            // Feed the existing Class factory explicit normal-layout Module
            // fixtures instead of pretending null denotes another named module.
            int fixtureModules=0;var bindModule=Fn<BindModule>(lib,"boom_java_class_bind_module");
            foreach(string line in File.ReadLines(Path.Combine(Path.GetDirectoryName(nameFile),"bootstrap-modules.tsv"))){
                string[] p=line.Split('\t');int id=int.Parse(p[0]),moduleType=int.Parse(p[1]),nameOffset=int.Parse(p[2]);IntPtr map=Marshal.ReadIntPtr(cp,40),table=Marshal.ReadIntPtr(map,16),layout=IntPtr.Zero;
                for(int i=0;i<Marshal.ReadInt32(map,8);i++){IntPtr row=IntPtr.Add(table,40*i);if(Marshal.ReadInt32(row,16)==moduleType&&Marshal.ReadInt32(row,20)==0){layout=Marshal.ReadIntPtr(row);break;}}
                Need(layout!=IntPtr.Zero,"Source Module fixture layout missing");Reset(ctx);IntPtr module=create(heap,layout,ctx);Need(module!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Module fixture allocation failed");
                Marshal.WriteIntPtr(module,nameOffset,String(heap,sp,ctx,p[3],create,alloc));Reset(ctx);Need(bindModule(cp,(uint)id,module,ctx)==1&&Marshal.ReadInt32(ctx)==0,"Source Module fixture bind failed");fixtureModules++;
            }
            long provided=0,unprovided=0,calls=0,bootCalls=0;var expected=new Dictionary<string,ulong>();var prepared=new List<IntPtr>();
            foreach(string line in File.ReadLines(nameFile)){
                string[] p=line.Split('\t');int id=int.Parse(p[0]),flags=int.Parse(p[1]);string name=HexName(p[2]);IntPtr s=String(heap,sp,ctx,name,create,alloc,(calls&1)==0);
                for(int i=0;i<32;i+=8)Marshal.WriteInt64(args,i,0);Marshal.WriteIntPtr(args,s);Reset(ctx);ulong mirror=lookup(ctx,args);calls++;
                if((flags&1)==0){Need(mirror==0&&Marshal.ReadInt32(ctx)==20,"Unavailable source type was hidden");unprovided++;}
                else{Need(mirror!=0&&Marshal.ReadInt32(ctx)==0,"Source lookup failed: "+name+", kind="+Marshal.ReadInt32(ctx));Need(typeid(ctx,cp,new IntPtr(unchecked((long)mirror)))==(uint)id&&Marshal.ReadInt32(ctx)==0,"Source represented Class differs");expected.Add(name,mirror);provided++;if(prepared.Count<64)prepared.Add(s);}
                Reset(ctx);ulong bootMirror=boot(ctx,args);bootCalls++;Need(bootMirror==mirror&&Marshal.ReadInt32(ctx)==((flags&1)==0?20:0),"Bootstrap native lookup differs");
            }
            long oracle=0;
            foreach(string line in File.ReadLines(oracleFile)){
                string[] p=line.Split('\t');Marshal.WriteIntPtr(args,String(heap,sp,ctx,p[0],create,alloc));for(int i=8;i<32;i+=8)Marshal.WriteInt64(args,i,0);Reset(ctx);ulong mirror=java(ctx,args);
                if(p[1]=="OK")Need(expected.ContainsKey(p[0])&&mirror==expected[p[0]]&&Marshal.ReadInt32(ctx)==0,"Original public forName differs from JVM: "+p[0]+", kind="+Marshal.ReadInt32(ctx));
                else Need(mirror==0&&Marshal.ReadInt32(ctx)==16,"Original forName CNFE kind differs: "+p[0]);oracle++;
            }
            string[] fields=File.ReadAllLines(enumFile);int enumId=int.Parse(fields[0].Split('\t')[0]);string targetName=fields[0].Split('\t')[1];IntPtr descriptor=NativeLibrary.GetExport(dll,"boom_class"+enumId);
            Need(Marshal.ReadInt32(descriptor,8)==0,"Lookup(false) initialized the enum");
            string arrayName="[L"+targetName+";";
            if(expected.ContainsKey(arrayName)){Marshal.WriteIntPtr(args,String(heap,sp,ctx,arrayName,create,alloc));Marshal.WriteInt64(args,8,1);Reset(ctx);Need(lookup(ctx,args)==expected[arrayName]&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt32(descriptor,8)==0,"Array lookup initialized its component");}
            IntPtr target=String(heap,sp,ctx,targetName,create,alloc);var initialized=new ulong[workers];
            using(var gate=new Barrier(workers))Parallel.For(0,workers,w=>{IntPtr c=Marshal.AllocHGlobal(32),a=Marshal.AllocHGlobal(32);try{Reset(c);for(int i=0;i<32;i+=8)Marshal.WriteInt64(a,i,0);Marshal.WriteIntPtr(a,target);Marshal.WriteInt64(a,8,1);gate.SignalAndWait();initialized[w]=lookup(c,a);Need(initialized[w]==expected[targetName]&&Marshal.ReadInt32(c)==0,"Lookup initializer failed kind="+Marshal.ReadInt32(c)+", state="+Marshal.ReadInt32(descriptor,8)+", row="+Marshal.ReadInt32(diagnostic,32)+", returned="+initialized[w]);}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});
            Need(Marshal.ReadInt32(descriptor,8)==2,"Original source enum initialization not published");var nameGetter=Fn<Entry>(dll,enumName);var ordinalGetter=Fn<Entry>(dll,enumOrdinal);int ordinal=0;
            foreach(string line in fields){string[] p=line.Split('\t');IntPtr value=Marshal.ReadIntPtr(NativeLibrary.GetExport(dll,"boom_s"+enumId+"_"+p[2]));Need(value!=IntPtr.Zero,"Original enum constant missing");Marshal.WriteIntPtr(args,value);Reset(ctx);IntPtr name=new IntPtr(unchecked((long)nameGetter(ctx,args)));Need(Marshal.ReadInt32(ctx)==0&&Text(sp,name)==p[3],"Original enum name differs");Reset(ctx);Need(ordinalGetter(ctx,args)==(ulong)ordinal++&&Marshal.ReadInt32(ctx)==0,"Original enum ordinal differs");}
            long before=Marshal.ReadInt64(heap,48);Parallel.For(0,workers,w=>{IntPtr c=Marshal.AllocHGlobal(32),a=Marshal.AllocHGlobal(32);try{for(int i=0;i<32;i+=8)Marshal.WriteInt64(a,i,0);for(int i=0;i<512;i++){Marshal.WriteIntPtr(a,prepared[(w+i)%prepared.Count]);Reset(c);Need(lookup(c,a)!=0&&Marshal.ReadInt32(c)==0,"Parallel source lookup failed");}}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});Need(Marshal.ReadInt64(heap,48)==before,"Warm source lookup allocated");
            int errors=0;Action<int,Func<ulong>> fail=(kind,invoke)=>{Reset(ctx);Need(invoke()==0&&Marshal.ReadInt32(ctx)==kind,"Lookup error differs expected="+kind+", actual="+Marshal.ReadInt32(ctx));errors++;};
            Marshal.WriteIntPtr(args,cold);for(int i=8;i<32;i+=8)Marshal.WriteInt64(args,i,0);Reset(ctx);Marshal.WriteInt32(ctx,99);Need(lookup(ctx,args)==0&&Marshal.ReadInt32(ctx)==99,"Pending lookup failure overwritten");errors++;
            Need(kernel(IntPtr.Zero,args,pool,0)==0,"Null lookup context accepted");errors++;fail(7,()=>kernel(ctx,IntPtr.Zero,pool,0));fail(7,()=>kernel(ctx,args,IntPtr.Zero,0));foreach(int op in new[]{2,-1,256})fail(7,()=>kernel(ctx,args,pool,op));
            Marshal.WriteIntPtr(args,IntPtr.Zero);fail(4,()=>lookup(ctx,args));Marshal.WriteIntPtr(args,cold);Marshal.WriteIntPtr(args,24,cold);fail(7,()=>lookup(ctx,args));Marshal.WriteIntPtr(args,24,IntPtr.Zero);
            Marshal.WriteIntPtr(args,16,cold);fail(7,()=>lookup(ctx,args));Marshal.WriteIntPtr(args,16,IntPtr.Zero);
            Marshal.WriteIntPtr(args,String(heap,sp,ctx,new string('[',255)+"I",create,alloc));fail(20,()=>lookup(ctx,args));
            Need(Marshal.ReadInt32(diagnostic,8)==0,"Source lookup reached an unimplemented dependency");
            Need(Marshal.ReadInt32(NativeLibrary.GetExport(dll,"boom_class"+Marshal.ReadInt32(pool,104)),8)==0,"Fixture unexpectedly initialized ClassLoader");
            return new long[]{workers,provided,unprovided,calls,bootCalls,oracle,ordinal,workers,workers*512,errors,fixtureModules};
        }finally{if(heap!=IntPtr.Zero)Need(destroy(heap)==1,"Source lookup heap cleanup failed");foreach(IntPtr p in owned)Marshal.FreeHGlobal(p);if(dll!=IntPtr.Zero){ReleaseTrace(dll);NativeLibrary.Free(dll);}NativeLibrary.Free(lib);}
    }
    static IntPtr String(IntPtr heap,IntPtr sp,IntPtr ctx,string value,New create,Alloc alloc,bool wide=false){
        Reset(ctx);IntPtr result=create(heap,Marshal.ReadIntPtr(sp,40),ctx);Need(result!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Lookup fixture String allocation failed");
        bool latin=!wide;foreach(char c in value)if(c>255)latin=false;
        byte[] bytes=latin?Encoding.Latin1.GetBytes(value):Encoding.Unicode.GetBytes(value);IntPtr data=alloc(heap,(ulong)bytes.Length,0,264);Need(data!=IntPtr.Zero,"Lookup fixture bytes failed");
        Marshal.Copy(bytes,0,data,bytes.Length);Marshal.WriteIntPtr(result,Marshal.ReadInt32(sp,48),data);Marshal.WriteByte(result,Marshal.ReadInt32(sp,52),(byte)(latin?0:1));return result;
    }
    public static int Smoke(string runtime,string image,int atomicId){
        IntPtr lib=NativeLibrary.Load(runtime),dll=IntPtr.Zero,heap=IntPtr.Zero;var owned=new List<IntPtr>();var destroy=Fn<Destroy>(lib,"boom_heap_destroy");
        try{
            dll=NativeLibrary.Load(image);heap=Fn<Create>(lib,"boom_heap_create")(64*1024*1024);Need(heap!=IntPtr.Zero&&Fn<Bind>(dll,"boom_java_string_literals_bind_heap")(heap)==1,"Lookup smoke heap failed");
            IntPtr ctx=Memory(owned,32),args=Memory(owned,32),cp=NativeLibrary.GetExport(dll,"boom_java_class_pool"),sp=NativeLibrary.GetExport(dll,"boom_java_string_literal_pool"),bp=NativeLibrary.GetExport(dll,"boom_java_class_bootstrap_pool");
            int cls=Marshal.ReadInt32(cp,108),cap=Marshal.ReadInt32(cp,12);Need(Fn<Ensure>(lib,"boom_class_ensure32")(NativeLibrary.GetExport(dll,"boom_class"+cls),ctx)==0&&Marshal.ReadInt32(ctx)==0,"Lookup smoke original Class init failed");
            string[] names={"java.lang.Class","java.util.concurrent.atomic.AtomicInteger"};int[] ids={cls,atomicId};
            var rows=new List<Tuple<uint,string,int>>();for(int i=0;i<names.Length;i++)rows.Add(Tuple.Create(Hash(names[i]),names[i],ids[i]));rows.Sort((a,b)=>a.Item1.CompareTo(b.Item1));
            IntPtr pool=Memory(owned,128),table=Memory(owned,rows.Count*32),text=Memory(owned,4096),init=Memory(owned,cap*16);int offset=0;
            for(int i=0;i<rows.Count;i++){var r=rows[i];Marshal.WriteInt32(table,i*32,offset);Marshal.WriteInt32(table,i*32+4,r.Item2.Length);Marshal.WriteInt32(table,i*32+8,unchecked((int)r.Item1));Marshal.WriteInt32(table,i*32+12,r.Item3);Marshal.WriteInt32(table,i*32+16,1);for(int n=0;n<r.Item2.Length;n++)Marshal.WriteInt16(text,(offset+n)*2,(short)r.Item2[n]);offset+=r.Item2.Length;}
            Marshal.WriteInt32(pool,0x4a43464e);Marshal.WriteInt32(pool,4,1);Marshal.WriteInt32(pool,8,cap);Marshal.WriteInt32(pool,12,rows.Count);
            Marshal.WriteIntPtr(pool,16,cp);Marshal.WriteIntPtr(pool,24,sp);Marshal.WriteIntPtr(pool,32,bp);Marshal.WriteIntPtr(pool,40,table);Marshal.WriteIntPtr(pool,48,init);Marshal.WriteIntPtr(pool,56,Marshal.ReadIntPtr(cp,48));
            Marshal.WriteInt32(pool,64,Marshal.ReadInt32(sp,48));Marshal.WriteInt32(pool,68,Marshal.ReadInt32(sp,52));Marshal.WriteIntPtr(pool,80,text);Marshal.WriteInt32(pool,88,offset);Marshal.WriteInt32(pool,92,32);Marshal.WriteInt32(pool,96,16);Marshal.WriteInt32(pool,100,cls);Marshal.WriteInt32(pool,108,1);
            var create=Fn<New>(lib,"boom_object_new");var alloc=Fn<Alloc>(lib,"boom_heap_alloc");var lookup=Fn<Lookup>(lib,"boom_java_class_lookup");var typeid=Fn<TypeId>(lib,"boom_java_class_typeid");int count=0;
            foreach(string n in names)foreach(bool wide in new[]{false,true}){IntPtr s=String(heap,sp,ctx,n,create,alloc,wide);Marshal.WriteIntPtr(args,s);Reset(ctx);ulong mirror=lookup(ctx,args,pool,0);Need(mirror!=0&&Marshal.ReadInt32(ctx)==0,"Lookup smoke failed "+n+", kind="+Marshal.ReadInt32(ctx));Need(typeid(ctx,cp,new IntPtr(unchecked((long)mirror)))==(uint)(n==names[0]?cls:atomicId),"Lookup smoke canonical type differs");count++;}
            Marshal.WriteIntPtr(args,String(heap,sp,ctx,"missing.Type",create,alloc));Reset(ctx);Need(lookup(ctx,args,pool,0)==0&&Marshal.ReadInt32(ctx)==16,"Lookup smoke CNFE differs");count++;Reset(ctx);Need(lookup(ctx,args,pool,1)==0&&Marshal.ReadInt32(ctx)==0,"Lookup bootstrap missing differs");count++;
            IntPtr atomic=NativeLibrary.GetExport(dll,"boom_class"+atomicId);Need(Marshal.ReadInt32(atomic,24)==atomicId&&Marshal.ReadInt32(atomic,8)==0,"Lookup smoke initializer descriptor was not cold/source-bound");
            Marshal.WriteIntPtr(init,atomicId*16,atomic);Marshal.WriteIntPtr(args,String(heap,sp,ctx,names[1],create,alloc));Marshal.WriteInt64(args,8,1);Reset(ctx);
            Need(lookup(ctx,args,pool,0)!=0&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt32(atomic,8)==2,"Lookup smoke did not execute the original AtomicInteger initializer");return count+1;
        }finally{if(heap!=IntPtr.Zero)Need(destroy(heap)==1,"Lookup smoke cleanup failed");foreach(IntPtr p in owned)Marshal.FreeHGlobal(p);if(dll!=IntPtr.Zero){ReleaseTrace(dll);NativeLibrary.Free(dll);}NativeLibrary.Free(lib);}
    }
}
