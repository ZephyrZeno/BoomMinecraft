using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;

// Development host only. Original System initialization, registration, clocks,
// allocation, arraycopy, runtime typing and explicit collection execute MASM.
public static class BoomBatchSystemProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(IntPtr ctx,IntPtr argv);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong size);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Make(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr NewArray(IntPtr heap,IntPtr counts,IntPtr type,uint dimensions,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Literal(IntPtr ctx,IntPtr pool,uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Collect(IntPtr heap,IntPtr roots,ulong count);
    sealed class Buffer {public IntPtr Pointer;public int Kind;}
    static T Symbol<T>(IntPtr m,string name) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(m,name));}
    // OFFSET an imported procedure names its PE jump thunk, not the final DLL
    // function address. Inspect loader-resolved IAT data instead of code bytes.
    static IntPtr ImportedAddress(IntPtr module,string library,string symbol){
        int pe=Marshal.ReadInt32(module,0x3c);IntPtr optional=IntPtr.Add(module,pe+24);
        Need(Marshal.ReadInt16(optional)==0x20b,"System module is not PE32+");
        int imports=Marshal.ReadInt32(optional,120);
        for(int index=0;index<128;index++){
            IntPtr descriptor=IntPtr.Add(module,imports+index*20);int lookup=Marshal.ReadInt32(descriptor),name=Marshal.ReadInt32(descriptor,12),iat=Marshal.ReadInt32(descriptor,16);
            if(name==0)break;
            if(!String.Equals(Marshal.PtrToStringAnsi(IntPtr.Add(module,name)),library,StringComparison.OrdinalIgnoreCase))continue;
            Need(lookup!=0&&iat!=0,"Missing System import names/addresses");
            for(int entry=0;entry<65536;entry++){
                long value=Marshal.ReadInt64(module,lookup+entry*8);if(value==0)break;if(value<0)continue;
                if(Marshal.PtrToStringAnsi(IntPtr.Add(module,checked((int)value)+2))==symbol)return Marshal.ReadIntPtr(module,iat+entry*8);
            }
        }
        throw new Exception("Missing System service import: "+symbol);
    }
    static void Need(bool condition,string text){if(!condition)throw new Exception(text);}
    static void Reset(IntPtr ctx){for(int i=0;i<32;i+=8)Marshal.WriteInt64(ctx,i,0);Marshal.WriteInt32(ctx,4,37);Marshal.WriteInt32(ctx,8,73);}
    static IntPtr Context(){IntPtr p=Marshal.AllocHGlobal(32);Reset(p);return p;}
    static void Error(IntPtr ctx,int kind){Need(Marshal.ReadInt32(ctx)==kind&&Marshal.ReadInt32(ctx,4)==37&&Marshal.ReadInt32(ctx,8)==73&&Marshal.ReadInt32(ctx,12)==0,"System native context/location differs");}
    static readonly string[] Descriptors={"[Z","[B","[C","[S","[I","[J","[F","[D"};
    static readonly int[] Sizes={1,1,2,2,4,8,4,8};
    static readonly ulong[][] Words={
        new ulong[]{1,0,1,1,0,0,1,0},new ulong[]{128,127,1,253,0,16,64,255},new ulong[]{0,65535,55296,1024,1,32,1000,2000},
        new ulong[]{32768,32767,1,65533,0,16,2000,65535},new ulong[]{0x80000000,0x7fffffff,1,0xfffffffd,0,16,2000,0xffffffff},
        new ulong[]{0x8000000000000000,0x7fffffffffffffff,1,0xfffffffffffffffd,0,16,2000,0xffffffffffffffff},
        new ulong[]{0x7fc00001,0x80000000,0x3fa00000,0xc0400000,0,0x41800000,0x44fa0000,0xbf800000},
        new ulong[]{0x7ff8000000000001,0x8000000000000000,0x3ff4000000000000,0xc008000000000000,0,0x4030000000000000,0x409f400000000000,0xbff0000000000000}};
    static string Snapshot(Buffer b,IntPtr a,IntPtr plain,IntPtr other){
        if(b.Pointer==IntPtr.Zero)return "-";if(b.Kind==-1)return "object";
        var text=new StringBuilder();
        if(b.Kind>=8){for(int i=0;i<8;i++){IntPtr p=Marshal.ReadIntPtr(b.Pointer,i*8);text.Append(p==IntPtr.Zero?'0':p==a?'1':p==plain?'2':p==other?'3':'?');}}
        else{int bytes=checked((int)Marshal.ReadInt64(b.Pointer,-16));for(int i=0;i<bytes;i++)text.Append(Marshal.ReadByte(b.Pointer,i).ToString("x2"));}
        return text.ToString();
    }
    public static long[] Run(string runtime,string dll,string directory,int systemClass,int objectClass,string registerName,string millisName,string nanosName,string copyName){
        IntPtr library=NativeLibrary.Load(runtime),module=IntPtr.Zero,heap=IntPtr.Zero,ctx=IntPtr.Zero,argv=IntPtr.Zero,counts=IntPtr.Zero,rootMemory=IntPtr.Zero;
        var destroy=Symbol<Destroy>(library,"boom_heap_destroy");
        try{
            module=NativeLibrary.Load(dll);ctx=Context();argv=Marshal.AllocHGlobal(40);counts=Marshal.AllocHGlobal(8);Marshal.WriteInt64(counts,8);
            IntPtr state=NativeLibrary.GetExport(module,"boom_class"+systemClass),pool=NativeLibrary.GetExport(module,"boom_batch_system_native_pool"),table=NativeLibrary.GetExport(module,"boom_batch_system_native_table");
            Need(Marshal.ReadInt32(state,8)==0&&Marshal.ReadIntPtr(pool,8)==IntPtr.Zero,"System began initialized or pre-registered");
            string[] targets={"boom_vm_current_time_millis","boom_vm_nano_time","boom_system_arraycopy"};
            for(int i=0;i<3;i++)Need(Marshal.ReadIntPtr(table,16+i*8)!=IntPtr.Zero&&ImportedAddress(module,"boom-runtime.dll",targets[i])==NativeLibrary.GetExport(library,targets[i]),"System service import did not resolve to real assembly runtime");
            var register=Symbol<Entry>(module,registerName);var millis=Symbol<Entry>(module,millisName);var nanos=Symbol<Entry>(module,nanosName);var copy=Symbol<Entry>(module,copyName);
            var rawMillis=Symbol<Entry>(module,millisName+"_native");var rawRegister=Symbol<Entry>(module,registerName+"_native");
            Need(rawMillis(ctx,IntPtr.Zero)==0,"Unregistered System service returned a value");Error(ctx,20);Reset(ctx);
            Marshal.WriteInt32(ctx,16);Marshal.WriteInt64(ctx,16,0x12345678);
            Need(register(ctx,IntPtr.Zero)==0&&rawRegister(ctx,IntPtr.Zero)==0&&Marshal.ReadIntPtr(pool,8)==IntPtr.Zero&&Marshal.ReadInt32(state,8)==0,"Pending error registered/initialized System");
            Error(ctx,16);Need(Marshal.ReadInt64(ctx,16)==0x12345678,"Pending root changed");Reset(ctx);
            const int workers=8,clockRounds=128;
            Parallel.For(0,workers,worker=>{IntPtr context=Context();try{for(int i=0;i<clockRounds;i++){
                long before=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();long actual=unchecked((long)millis(context,IntPtr.Zero));long after=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
                Need(Marshal.ReadInt32(context)==0&&actual>=before-1&&actual<=after+1,"Live System millisecond clock is outside host time bracket");
                ulong first=nanos(context,IntPtr.Zero),last=nanos(context,IntPtr.Zero);Need(Marshal.ReadInt32(context)==0&&last>=first,"System monotonic clock moved backwards");
            }}finally{Marshal.FreeHGlobal(context);}});
            Need(Marshal.ReadInt32(state,8)==2&&Marshal.ReadIntPtr(pool,8)==table,"Original System clinit did not publish complete registration");
            for(int i=0;i<64;i++)Need(register(ctx,IntPtr.Zero)==0&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadIntPtr(pool,8)==table,"Idempotent registration changed table");
            heap=Symbol<Create>(library,"boom_heap_create")(16*1024*1024);Need(heap!=IntPtr.Zero&&Symbol<Bind>(module,"boom_java_string_literals_bind_heap")(heap)==1,"System test heap failed");
            var allocate=Symbol<NewArray>(library,"boom_typed_multi_new");var make=Symbol<Make>(library,"boom_object_new");var collect=Symbol<Collect>(library,"boom_heap_collect");
            IntPtr map=NativeLibrary.GetExport(module,"boom_runtime_type_map"),types=NativeLibrary.GetExport(module,"boom_batch_type_descriptors"),rows=Marshal.ReadIntPtr(map,16),layout=IntPtr.Zero;
            for(int i=0;i<Marshal.ReadInt32(map,8);i++){IntPtr row=IntPtr.Add(rows,i*40);if(Marshal.ReadInt32(row,16)==objectClass){layout=Marshal.ReadIntPtr(row);break;}}
            Need(layout!=IntPtr.Zero,"Source Object layout missing");IntPtr plain=make(heap,layout,ctx);
            var literal=Symbol<Literal>(module,"boom_java_string_literal");IntPtr literals=NativeLibrary.GetExport(module,"boom_java_string_literal_pool");IntPtr a=literal(ctx,literals,0),b=literal(ctx,literals,1);
            Need(plain!=IntPtr.Zero&&a!=IntPtr.Zero&&b!=IntPtr.Zero&&a!=b&&Marshal.ReadInt32(ctx)==0,"System reference seed allocation failed");
            var arrays=new Dictionary<string,int>();foreach(string line in File.ReadLines(Path.Combine(directory,"arrays.tsv"))){string[] p=line.Split('\t');arrays[p[0]]=int.Parse(p[1]);}
            Func<string,IntPtr> newArray=descriptor=>{IntPtr value=allocate(heap,counts,Marshal.ReadIntPtr(types,arrays[descriptor]*8),1,ctx);Need(value!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Source array allocation failed");return value;};
            Func<int,bool,Buffer> primitive=(kind,dest)=>{IntPtr value=newArray(Descriptors[kind]);for(int i=0;i<8;i++){ulong word=Words[kind][dest?7-i:i];for(int j=0;j<Sizes[kind];j++)Marshal.WriteByte(value,i*Sizes[kind]+j,(byte)(word>>(8*j)));}return new Buffer{Pointer=value,Kind=kind};};
            Func<string,int[],Buffer> references=(descriptor,values)=>{IntPtr value=newArray(descriptor);for(int i=0;i<8;i++)Marshal.WriteIntPtr(value,i*8,values[i]==0?IntPtr.Zero:values[i]==1?a:values[i]==2?plain:b);return new Buffer{Pointer=value,Kind=8};};
            Func<int,bool,Buffer> create=(kind,dest)=>{
                if(kind<8)return primitive(kind,dest);
                switch(kind){
                    case 8:return references("[Ljava/lang/String;",dest?new int[]{3,1,0,3,1,3,0,1}:new int[]{1,0,3,1,3,0,1,3});
                    case 9:return references(dest?"[Ljava/lang/Object;":"[Ljava/lang/String;",dest?new int[]{2,2,2,2,2,2,2,2}:new int[]{1,0,3,1,3,0,1,3});
                    case 10:return references(dest?"[Ljava/lang/String;":"[Ljava/lang/Object;",dest?new int[]{3,3,3,3,3,3,3,3}:new int[]{1,0,3,2,1,0,3,1});
                    case 11:return references(dest?"[Ljava/lang/String;":"[Ljava/lang/Object;",dest?new int[]{3,3,3,3,3,3,3,3}:new int[8]);
                    case 12:return primitive(dest?1:0,dest);case 13:return primitive(dest?5:4,dest);
                    case 14:return dest?references("[Ljava/lang/Object;",new int[8]):primitive(4,false);
                    case 15:return dest?primitive(4,true):new Buffer{Pointer=plain,Kind=-1};
                    case 16:return dest?new Buffer{Pointer=plain,Kind=-1}:primitive(4,false);
                    case 17:return dest?primitive(4,true):new Buffer();case 18:return dest?new Buffer():primitive(4,false);
                    case 19:return dest?new Buffer():new Buffer{Pointer=plain,Kind=-1};default:throw new Exception("Unknown oracle kind");
                }
            };
            long cases=0;
            foreach(string line in File.ReadLines(Path.Combine(directory,"oracle.tsv"))){string[] p=line.Split('\t');Reset(ctx);int kind=int.Parse(p[0]);Buffer source=create(kind,false),destination=p[1]=="1"?source:create(kind,true);
                Marshal.WriteIntPtr(argv,source.Pointer);Marshal.WriteInt64(argv,8,int.Parse(p[2]));Marshal.WriteIntPtr(argv,16,destination.Pointer);Marshal.WriteInt64(argv,24,int.Parse(p[3]));Marshal.WriteInt64(argv,32,int.Parse(p[4]));
                long used=Marshal.ReadInt64(heap,48);copy(ctx,argv);
                Need(Marshal.ReadInt32(ctx)==int.Parse(p[5]),"System.arraycopy error precedence differs at "+cases);
                Need(Snapshot(source,a,plain,b)==p[6]&&Snapshot(destination,a,plain,b)==p[7],"System.arraycopy snapshot differs at "+cases);
                Need(Marshal.ReadInt64(heap,48)==used,"System.arraycopy allocated hidden guest data");cases++;
            }
            Reset(ctx);copy(ctx,IntPtr.Zero);Error(ctx,7);Reset(ctx);
            const int copyRounds=1024;var parallel=new Buffer[workers];for(int i=0;i<workers;i++)parallel[i]=primitive(4,false);
            long warm=Marshal.ReadInt64(heap,48);
            Parallel.For(0,workers,worker=>{IntPtr context=Context(),args=Marshal.AllocHGlobal(40);try{IntPtr value=parallel[worker].Pointer;
                Marshal.WriteIntPtr(args,value);Marshal.WriteInt64(args,8,0);Marshal.WriteIntPtr(args,16,value);Marshal.WriteInt64(args,24,2);Marshal.WriteInt64(args,32,6);
                for(int n=0;n<copyRounds;n++){Reset(context);for(int i=0;i<8;i++)Marshal.WriteInt32(value,i*4,n+i);copy(context,args);Need(Marshal.ReadInt32(context)==0,"Parallel System copy failed");
                    for(int i=0;i<8;i++)Need(Marshal.ReadInt32(value,i*4)==n+(i<2?i:i-2),"Parallel overlapping copy changed data");}
            }finally{Marshal.FreeHGlobal(context);Marshal.FreeHGlobal(args);}});
            Need(Marshal.ReadInt64(heap,48)==warm,"Parallel System copy allocated guest data");
            rootMemory=Marshal.AllocHGlobal(24);Marshal.WriteIntPtr(rootMemory,plain);Marshal.WriteIntPtr(rootMemory,8,a);Marshal.WriteIntPtr(rootMemory,16,b);
            long freed=collect(heap,rootMemory,3);Need(freed>0,"System copy temporary arrays were not reclaimed");
            return new long[]{cases,workers*clockRounds*3L,workers*copyRounds,workers,freed};
        }finally{if(rootMemory!=IntPtr.Zero)Marshal.FreeHGlobal(rootMemory);foreach(IntPtr p in new IntPtr[]{ctx,argv,counts})if(p!=IntPtr.Zero)Marshal.FreeHGlobal(p);if(heap!=IntPtr.Zero)destroy(heap);if(module!=IntPtr.Zero)NativeLibrary.Free(module);NativeLibrary.Free(library);}
    }
}
