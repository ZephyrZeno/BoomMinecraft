using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

// Development FFI driver. Memory access and atomic work always execute MASM.
public static class BoomNormalUnsafeMemoryProbe {
    static Func<int,ulong> Cookies(IntPtr pool){int abi=Marshal.ReadInt32(pool,4);ulong tag=unchecked((ulong)Marshal.ReadInt64(pool,112));Need((abi==1&&tag==0x55464c4400000000UL)||(abi==2&&tag==0x55464c3200000000UL),"Unknown source field cookie ABI");return id=>tag|(abi==1?(uint)(id+1):((ulong)(uint)(id+1)<<8)|0x80UL);}
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr cls,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr NewObject(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr heap,ulong bytes,ulong refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Kernel(IntPtr ctx,IntPtr args,IntPtr pool,int op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(IntPtr ctx,IntPtr args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Contains(IntPtr heap,IntPtr obj);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Collect(IntPtr heap,IntPtr spans,ulong count);
    static T Fn<T>(IntPtr lib,string n) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(lib,n));}
    static void Need(bool value,string message){if(!value)throw new Exception(message);}
    static void Reset(IntPtr ctx){for(int i=0;i<32;i+=8)Marshal.WriteInt64(ctx,i,0);Marshal.WriteInt32(ctx,4,17);Marshal.WriteInt32(ctx,8,31);}
    static IntPtr Memory(List<IntPtr> memory,int size){IntPtr p=Marshal.AllocHGlobal(size);for(int i=0;i<size;i++)Marshal.WriteByte(p,i,0);memory.Add(p);return p;}
    static Dictionary<int,IntPtr> Layouts(IntPtr pool){
        var result=new Dictionary<int,IntPtr>();IntPtr map=Marshal.ReadIntPtr(pool,32),rows=Marshal.ReadIntPtr(map,16);
        for(int i=0;i<Marshal.ReadInt32(map,8);i++){IntPtr row=IntPtr.Add(rows,40*i);if(Marshal.ReadInt32(row,20)==0)result.Add(Marshal.ReadInt32(row,16),Marshal.ReadIntPtr(row));}return result;
    }
    static void Arguments(IntPtr a,IntPtr receiver,IntPtr obj,ulong offset,ulong expected=0,ulong desired=0){
        Marshal.WriteIntPtr(a,receiver);Marshal.WriteIntPtr(a,8,obj);Marshal.WriteInt64(a,16,unchecked((long)offset));Marshal.WriteInt64(a,24,unchecked((long)expected));Marshal.WriteInt64(a,32,unchecked((long)desired));
    }
    sealed class Field {public int Id,Class,Width,Offset;public IntPtr Object;public ulong Cookie;}
    static ulong Normal(int kind,ulong value){unchecked{switch(kind){case 1:return value&1;case 2:return (ulong)(long)(sbyte)value;case 3:return (ushort)value;case 4:return (ulong)(long)(short)value;case 5:return (ulong)(long)(int)value;case 7:return (uint)value;default:return value;}}}
    static bool Signaling(int kind,ulong bits){if(kind==7){uint n=(uint)bits;return (n&0x7f800000)==0x7f800000&&(n&0x007fffff)!=0&&(n&0x00400000)==0;}return kind==8&&(bits&0x7ff0000000000000UL)==0x7ff0000000000000UL&&(bits&0x000fffffffffffffUL)!=0&&(bits&0x0008000000000000UL)==0;}
    static bool Nan(int kind,ulong bits){return kind==7?((uint)bits&0x7fffffff)>0x7f800000:kind==8&&(bits&0x7fffffffffffffffUL)>0x7ff0000000000000UL;}

    public static long[] Run(string runtime,string image,string fieldFile,string methodFile,string oracleFile,
        int unsafeId,int singleton,int atomicId,int atomicField,int objectId,int arrayId,int loaderRoots,int moduleRoots,string[] javaEntries) {
        IntPtr lib=NativeLibrary.Load(runtime),dll=IntPtr.Zero,heap=IntPtr.Zero,other=IntPtr.Zero;var memory=new List<IntPtr>();var destroy=Fn<Destroy>(lib,"boom_heap_destroy");
        try{
            dll=NativeLibrary.Load(image);heap=Fn<Create>(lib,"boom_heap_create")(128UL*1024*1024);Need(heap!=IntPtr.Zero&&Fn<Bind>(dll,"boom_java_string_literals_bind_heap")(heap)==1,"Typed source heap bind failed");
            IntPtr ctx=Memory(memory,32),args=Memory(memory,40),pool=NativeLibrary.GetExport(dll,"boom_java_unsafe_field_pool");
            var cookieOf=Cookies(pool);ulong tag=unchecked((ulong)Marshal.ReadInt64(pool,112));
            var ensure=Fn<Ensure>(lib,"boom_class_ensure32");var create=Fn<NewObject>(lib,"boom_object_new");var alloc=Fn<Alloc>(lib,"boom_heap_alloc");var kernel=Fn<Kernel>(lib,"boom_java_unsafe_memory");
            var contains=Fn<Contains>(lib,"boom_heap_contains");var collect=Fn<Collect>(lib,"boom_heap_collect_spans");var layouts=Layouts(pool);
            IntPtr unsafeClass=NativeLibrary.GetExport(dll,"boom_class"+unsafeId);Need(Marshal.ReadInt32(unsafeClass,8)==0,"Unsafe was preinitialized");
            const int workers=8,iterations=512;
            using(var gate=new Barrier(workers))Parallel.For(0,workers,w=>{IntPtr c=Marshal.AllocHGlobal(32);try{Reset(c);gate.SignalAndWait();Need(ensure(unsafeClass,c)==0&&Marshal.ReadInt32(c)==0,"Original Unsafe init failed");}finally{Marshal.FreeHGlobal(c);}});
            IntPtr receiver=Marshal.ReadIntPtr(NativeLibrary.GetExport(dll,"boom_s"+unsafeId+"_"+singleton));Need(receiver!=IntPtr.Zero,"Missing original Unsafe receiver");
            var roots=new List<IntPtr>{receiver};var fields=new Dictionary<int,Field>();
            Func<int,IntPtr> objectOf=id=>{Reset(ctx);IntPtr value=create(heap,layouts[id],ctx);Need(value!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Typed fixture object allocation failed");roots.Add(value);return value;};
            foreach(string line in File.ReadLines(fieldFile)){string[] p=line.Split('\t');int kind=int.Parse(p[0]);var f=new Field{Id=int.Parse(p[1]),Class=int.Parse(p[2]),Width=int.Parse(p[3]),Offset=int.Parse(p[4])};f.Cookie=cookieOf(f.Id);f.Object=objectOf(f.Class);fields.Add(kind,f);}
            var entries=new Dictionary<int,Entry>();foreach(string line in File.ReadLines(methodFile)){string[] p=line.Split('\t');entries.Add(int.Parse(p[0]),Fn<Entry>(dll,p[1]));}Need(entries.Count==42,"Typed entry coverage differs");
            var arrays=new Dictionary<int,IntPtr>();int[] tags={0,260,264,261,265,266,267,262,263};
            for(int kind=1;kind<=8;kind++){IntPtr value=alloc(heap,64,0,(ulong)tags[kind]);Need(value!=IntPtr.Zero,"Primitive array fixture allocation failed");arrays.Add(kind,value);roots.Add(value);}
            IntPtr map=Marshal.ReadIntPtr(pool,32),rowTable=Marshal.ReadIntPtr(map,16),arrayTag=IntPtr.Zero;
            for(int i=0;i<Marshal.ReadInt32(map,8);i++){IntPtr rowData=IntPtr.Add(rowTable,40*i);if(Marshal.ReadInt32(rowData,16)==arrayId&&Marshal.ReadInt32(rowData,20)==2)arrayTag=Marshal.ReadIntPtr(rowData);}
            Need(arrayTag!=IntPtr.Zero,"Reference array source type missing");IntPtr refs=alloc(heap,32,4,unchecked((ulong)arrayTag.ToInt64()));Need(refs!=IntPtr.Zero,"Reference array fixture failed");arrays.Add(9,refs);roots.Add(refs);
            IntPtr one=objectOf(objectId),two=objectOf(objectId);ulong[] identities={0,unchecked((ulong)one.ToInt64()),unchecked((ulong)two.ToInt64())};
            long calls=0,quiet=0,vectors=0,atomics=0,views=0;
            Func<int,IntPtr,ulong,ulong,ulong,ulong> call=(op,target,offset,value,desired)=>{
                Arguments(args,receiver,target,offset,value,desired);Reset(ctx);long before=Marshal.ReadInt64(heap,48);ulong result=entries[op](ctx,args);
                Need(Marshal.ReadInt32(ctx)==0,"Typed source entry failed op="+op+", kind="+Marshal.ReadInt32(ctx));Need(Marshal.ReadInt64(heap,48)==before,"Typed native allocated");calls++;return result;
            };
            foreach(string line in File.ReadLines(oracleFile)){
                string[] p=line.Split('\t');int kind=int.Parse(p[0]);ulong bits=Convert.ToUInt64(p[1],16),expected=Normal(kind,bits);int column=2;
                for(int storage=0;storage<2;storage++){
                    IntPtr target=storage==0?fields[kind].Object:arrays[kind];ulong offset=storage==0?fields[kind].Cookie:0;
                    foreach(int store in new[]{1,3}){
                        call(store*16+kind,target,offset,bits,0);
                        foreach(int read in new[]{0,2}){
                            ulong actual=call(read*16+kind,target,offset,0,0),observed=Convert.ToUInt64(p[column++],16);
                            Need(actual==expected,"Typed raw bits differ kind="+kind+", input="+bits.ToString("x"));
                            if(observed!=expected){Need(Signaling(kind,bits)&&Nan(kind,observed),"JVM typed value differs kind="+kind);quiet++;}
                        }
                    }
                }
                Need(column==p.Length,"JVM vector shape differs");vectors++;
            }
            // All six CAS/exchange entries, success and failure, both domains.
            foreach(int kind in new[]{5,6,9})for(int storage=0;storage<2;storage++)for(int initial=0;initial<3;initial++)for(int expected=0;expected<3;expected++)for(int desired=0;desired<3;desired++){
                IntPtr target=storage==0?fields[kind].Object:arrays[kind];ulong offset=storage==0?fields[kind].Cookie:0;
                ulong v=kind==9?identities[initial]:(ulong)initial,e=kind==9?identities[expected]:(ulong)expected,d=kind==9?identities[desired]:(ulong)desired;
                call(16+kind,target,offset,v,0);Need(call(64+kind,target,offset,e,d)==(initial==expected?1UL:0UL),"CAS boolean differs");
                Need(call(kind,target,offset,0,0)==(initial==expected?d:v),"CAS final value differs");
                call(16+kind,target,offset,v,0);Need(call(80+kind,target,offset,e,d)==v,"Exchange witness differs");
                Need(call(32+kind,target,offset,0,0)==(initial==expected?d:v),"Exchange final value differs");atomics+=2;
            }
            // Scalar aliases used by Java float/double atomic wrappers.
            foreach(int kind in new[]{5,6}){
                int floating=kind==5?7:8;ulong a=kind==5?0x7f812345UL:0x7ff0123456789abcUL,b=kind==5?0x80000000UL:0x8000000000000000UL;
                call(16+floating,fields[floating].Object,fields[floating].Cookie,a,0);
                Need(call(64+kind,fields[floating].Object,fields[floating].Cookie,a,b)==1&&call(floating,fields[floating].Object,fields[floating].Cookie,0,0)==b,"Floating field CAS alias differs");atomics++;
            }
            // Boundaries, random values and wraparound witnesses for I/J CAS.
            foreach(int kind in new[]{5,6})foreach(ulong raw in new[]{0UL,1UL,0x7fffffffUL,0x80000000UL,0xffffffffUL,0x8000000000000000UL,ulong.MaxValue})for(int storage=0;storage<2;storage++){
                IntPtr target=storage==0?fields[kind].Object:arrays[kind];ulong offset=storage==0?fields[kind].Cookie:0;
                ulong value=Normal(kind,raw),desired=Normal(kind,raw^0xa5a5a5a5a5a5a5a5UL);call(16+kind,target,offset,raw,0);
                Need(call(80+kind,target,offset,raw,desired)==value&&call(kind,target,offset,0,0)==desired,"Boundary exchange witness differs");atomics++;
            }
            // Unaligned ordinary byte views, without altering reference regions.
            foreach(int kind in new[]{2,3,4,5,6,7,8})foreach(ulong offset in new[]{1UL,3UL,7UL}){
                ulong value=0xabcdef9876543210UL;call(16+kind,arrays[2],offset,value,0);Need(call(kind,arrays[2],offset,0,0)==Normal(kind,value),"Primitive byte view differs");views++;
            }
            call(18,fields[1].Object,fields[1].Cookie,0xfe,0);Need(call(1,fields[1].Object,fields[1].Cookie,0,0)==1,"Boolean nonzero normalization differs");views++;
            long contentions=0;
            foreach(int kind in new[]{5,6,9})for(int storage=0;storage<2;storage++){
                IntPtr target=storage==0?fields[kind].Object:arrays[kind];ulong offset=storage==0?fields[kind].Cookie:0;
                call(16+kind,target,offset,kind==9?identities[1]:0,0);long before=Marshal.ReadInt64(heap,48);
                Parallel.For(0,workers,w=>{
                    IntPtr c=Marshal.AllocHGlobal(32),a=Marshal.AllocHGlobal(40);try{
                        for(int i=0;i<iterations;i++)while(true){
                            Arguments(a,receiver,target,offset);Reset(c);ulong old=entries[32+kind](c,a);Need(Marshal.ReadInt32(c)==0,"Contention read failed");
                            ulong next=kind==9?(old==identities[1]?identities[2]:identities[1]):old+1;
                            Arguments(a,receiver,target,offset,old,next);Reset(c);ulong changed=entries[64+kind](c,a);Need(Marshal.ReadInt32(c)==0,"Contention CAS failed");if(changed!=0)break;
                        }
                    }finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}
                });
                ulong expected=kind==9?identities[1]:(ulong)(workers*iterations);Need(call(kind,target,offset,0,0)==expected&&Marshal.ReadInt64(heap,48)==before,"Lost atomic update or allocation under contention");contentions+=workers*iterations;
            }
            int litmus=128;IntPtr x=arrays[5],y=fields[5].Object;ulong yOffset=fields[5].Cookie;int[] outcomes=new int[2];
            using(var gate=new Barrier(2)){
                var tasks=new Task[2];
                for(int thread=0;thread<2;thread++){int t=thread;tasks[t]=Task.Run(()=>{
                    IntPtr c=Marshal.AllocHGlobal(32),a=Marshal.AllocHGlobal(40);try{for(int round=0;round<litmus;round++){
                        if(t==0){Arguments(a,receiver,x,0,0);Reset(c);entries[21](c,a);Need(Marshal.ReadInt32(c)==0,"Litmus reset failed");Arguments(a,receiver,y,yOffset,0);Reset(c);entries[21](c,a);Need(Marshal.ReadInt32(c)==0,"Litmus reset failed");}
                        gate.SignalAndWait();Arguments(a,receiver,t==0?x:y,t==0?0:yOffset,1);Reset(c);entries[53](c,a);Need(Marshal.ReadInt32(c)==0,"Litmus volatile store failed");
                        Arguments(a,receiver,t==0?y:x,t==0?yOffset:0);Reset(c);outcomes[t]=(int)entries[37](c,a);Need(Marshal.ReadInt32(c)==0,"Litmus volatile load failed");gate.SignalAndWait();
                        if(t==0)Need(outcomes[0]!=0||outcomes[1]!=0,"Forbidden both-zero SC outcome");gate.SignalAndWait();
                    }}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}
                });}Task.WaitAll(tasks);
            }
            Reset(ctx);Need(ensure(NativeLibrary.GetExport(dll,"boom_class"+atomicId),ctx)==0&&Marshal.ReadInt32(ctx)==0,"Original AtomicInteger initializer failed");
            var ctor=Fn<Entry>(dll,javaEntries[0]);var get=Fn<Entry>(dll,javaEntries[1]);var cas=Fn<Entry>(dll,javaEntries[2]);var increment=Fn<Entry>(dll,javaEntries[3]);IntPtr atomicObject=objectOf(atomicId);ulong atomicCookie=cookieOf(atomicField);
            Arguments(args,atomicObject,IntPtr.Zero,0);Marshal.WriteInt64(args,8,41);Reset(ctx);ctor(ctx,args);Need(Marshal.ReadInt32(ctx)==0,"Original atomic constructor failed");
            Marshal.WriteIntPtr(args,atomicObject);Marshal.WriteInt64(args,8,41);Marshal.WriteInt64(args,16,42);Reset(ctx);Need(cas(ctx,args)==1&&Marshal.ReadInt32(ctx)==0,"Original compareAndSet source failed");
            Marshal.WriteIntPtr(args,atomicObject);Reset(ctx);Need(increment(ctx,args)==42&&Marshal.ReadInt32(ctx)==0,"Original getAndIncrement source failed");
            call(21,atomicObject,atomicCookie,0,0);
            Parallel.For(0,workers,w=>{IntPtr c=Marshal.AllocHGlobal(32),a=Marshal.AllocHGlobal(8);try{Marshal.WriteIntPtr(a,atomicObject);for(int i=0;i<iterations;i++){Reset(c);increment(c,a);Need(Marshal.ReadInt32(c)==0,"Original Java atomic loop failed");}}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});
            Marshal.WriteIntPtr(args,atomicObject);Reset(ctx);Need(get(ctx,args)==(ulong)(workers*iterations)&&Marshal.ReadInt32(ctx)==0,"Original Java atomic loop lost increments");long javaCalls=workers*iterations;
            int errors=0;
            Action<int,Func<ulong>> fail=(kind,invoke)=>{Reset(ctx);Need(invoke()==0&&Marshal.ReadInt32(ctx)==kind,"Typed error kind differs, expected="+kind+", actual="+Marshal.ReadInt32(ctx));errors++;};
            Arguments(args,receiver,fields[5].Object,fields[5].Cookie);Reset(ctx);Marshal.WriteInt32(ctx,99);long pendingUsed=Marshal.ReadInt64(heap,48);
            Need(entries[69](ctx,args)==0&&Marshal.ReadInt32(ctx)==99&&Marshal.ReadInt32(ctx,4)==17&&Marshal.ReadInt64(heap,48)==pendingUsed,"Pending typed error overwritten");errors++;
            Need(kernel(IntPtr.Zero,args,pool,69)==0,"Null memory context accepted");errors++;
            fail(7,()=>kernel(ctx,IntPtr.Zero,pool,69));fail(7,()=>kernel(ctx,args,IntPtr.Zero,69));
            foreach(int op in new[]{0,10,15,65,68,71,90,101,0x10005,-1})fail(7,()=>kernel(ctx,args,pool,op));
            Marshal.WriteIntPtr(args,IntPtr.Zero);fail(4,()=>entries[69](ctx,args));Marshal.WriteIntPtr(args,receiver);
            Arguments(args,receiver,IntPtr.Zero,0);fail(20,()=>entries[5](ctx,args));
            Arguments(args,receiver,fields[9].Object,fields[9].Cookie);fail(7,()=>entries[6](ctx,args));
            Arguments(args,receiver,fields[6].Object,fields[6].Cookie);fail(7,()=>entries[9](ctx,args));
            Arguments(args,receiver,fields[5].Object,fields[5].Cookie);fail(7,()=>entries[6](ctx,args));
            Arguments(args,receiver,arrays[9],0);fail(20,()=>entries[5](ctx,args));Arguments(args,receiver,arrays[5],0);fail(7,()=>entries[9](ctx,args));
            Arguments(args,receiver,arrays[2],1);fail(20,()=>entries[37](ctx,args));fail(20,()=>entries[69](ctx,args));
            foreach(ulong offset in new[]{ulong.MaxValue,64UL,63UL}){Arguments(args,receiver,arrays[2],offset);fail(7,()=>entries[6](ctx,args));}
            foreach(ulong token in new[]{tag,cookieOf(Marshal.ReadInt32(pool,12))}){Arguments(args,receiver,fields[5].Object,token);fail(7,()=>entries[5](ctx,args));}
            Arguments(args,receiver,fields[5].Object,0);fail(20,()=>entries[5](ctx,args));
            other=Fn<Create>(lib,"boom_heap_create")(1024*1024);Need(other!=IntPtr.Zero,"Foreign memory heap fixture failed");Reset(ctx);IntPtr foreign=create(other,layouts[objectId],ctx);Need(foreign!=IntPtr.Zero,"Foreign memory object failed");
            Arguments(args,receiver,fields[9].Object,fields[9].Cookie,unchecked((ulong)foreign.ToInt64()));fail(7,()=>entries[25](ctx,args));
            Arguments(args,receiver,fields[9].Object,fields[9].Cookie,unchecked((ulong)foreign.ToInt64()),identities[1]);fail(7,()=>entries[73](ctx,args));
            Arguments(args,receiver,foreign,fields[5].Cookie);fail(7,()=>entries[5](ctx,args));
            // Explicit quiescent collection verifies reference-prefix writes and
            // clearing CAS without introducing an automatic collector.
            Reset(ctx);IntPtr child=create(heap,layouts[objectId],ctx);Need(child!=IntPtr.Zero,"Reference collection fixture allocation failed");
            call(25,fields[9].Object,fields[9].Cookie,unchecked((ulong)child.ToInt64()),0);
            IntPtr fixtureCells=Memory(memory,roots.Count*8);for(int i=0;i<roots.Count;i++)Marshal.WriteIntPtr(fixtureCells,i*8,roots[i]);
            var regions=new List<Tuple<IntPtr,long>>();
            regions.Add(Tuple.Create(NativeLibrary.GetExport(dll,"boom_probe_static_roots"),Marshal.ReadInt64(NativeLibrary.GetExport(dll,"boom_probe_static_root_count"))));
            regions.Add(Tuple.Create(Marshal.ReadIntPtr(NativeLibrary.GetExport(dll,"boom_java_string_literal_pool"),24),Marshal.ReadInt64(NativeLibrary.GetExport(dll,"boom_java_string_literal_root_count"))));
            regions.Add(Tuple.Create(NativeLibrary.GetExport(dll,"boom_java_class_roots"),Marshal.ReadInt64(NativeLibrary.GetExport(dll,"boom_java_class_root_count"))));
            regions.Add(Tuple.Create(NativeLibrary.GetExport(dll,"boom_java_class_name_roots"),Marshal.ReadInt64(NativeLibrary.GetExport(dll,"boom_java_class_name_root_count"))));
            regions.Add(Tuple.Create(NativeLibrary.GetExport(dll,"boom_java_class_loader_roots"),(long)loaderRoots));regions.Add(Tuple.Create(NativeLibrary.GetExport(dll,"boom_java_class_module_roots"),(long)moduleRoots));
            regions.Add(Tuple.Create(fixtureCells,(long)roots.Count));IntPtr spans=Memory(memory,regions.Count*16);
            for(int i=0;i<regions.Count;i++){Marshal.WriteIntPtr(spans,i*16,regions[i].Item1);Marshal.WriteInt64(spans,i*16+8,regions[i].Item2);}
            Need(collect(heap,spans,(ulong)regions.Count)>=0&&contains(heap,child)==1&&call(9,fields[9].Object,fields[9].Cookie,0,0)==unchecked((ulong)child.ToInt64()),"New reference store lost child at quiescent collection");
            Need(call(73,fields[9].Object,fields[9].Cookie,unchecked((ulong)child.ToInt64()),0)==1,"Reference clearing CAS failed");
            Need(collect(heap,spans,(ulong)regions.Count)>=0&&contains(heap,child)==0,"Cleared reference retained unreachable child");
            Need(Marshal.ReadInt32(NativeLibrary.GetExport(dll,"boom_diagnostic_pool"),8)==0,"Typed fixture reached unimplemented source dependency");
            return new long[]{workers,vectors,calls,quiet,atomics,views,contentions,litmus,javaCalls,errors,2,entries.Count};
        }finally{if(other!=IntPtr.Zero)Need(destroy(other)==1,"Foreign memory cleanup failed");if(heap!=IntPtr.Zero)Need(destroy(heap)==1,"Typed memory heap cleanup failed");for(int i=memory.Count-1;i>=0;i--)Marshal.FreeHGlobal(memory[i]);if(dll!=IntPtr.Zero)NativeLibrary.Free(dll);NativeLibrary.Free(lib);}
    }
    public static long Smoke(string runtime,string image,int unsafeId,int singleton,int atomicId,int valueField){
        IntPtr lib=NativeLibrary.Load(runtime),dll=IntPtr.Zero,heap=IntPtr.Zero;var memory=new List<IntPtr>();var destroy=Fn<Destroy>(lib,"boom_heap_destroy");
        try{
            dll=NativeLibrary.Load(image);heap=Fn<Create>(lib,"boom_heap_create")(64UL*1024*1024);Need(heap!=IntPtr.Zero&&Fn<Bind>(dll,"boom_java_string_literals_bind_heap")(heap)==1,"Memory kernel fixture heap bind failed");
            IntPtr ctx=Memory(memory,32),args=Memory(memory,40),pool=NativeLibrary.GetExport(dll,"boom_java_unsafe_field_pool");
            Reset(ctx);Need(Fn<Ensure>(lib,"boom_class_ensure32")(NativeLibrary.GetExport(dll,"boom_class"+unsafeId),ctx)==0&&Marshal.ReadInt32(ctx)==0,"Original Unsafe kernel fixture init failed");
            IntPtr receiver=Marshal.ReadIntPtr(NativeLibrary.GetExport(dll,"boom_s"+unsafeId+"_"+singleton));
            var layouts=Layouts(pool);Reset(ctx);IntPtr obj=Fn<NewObject>(lib,"boom_object_new")(heap,layouts[atomicId],ctx);Need(obj!=IntPtr.Zero,"Memory kernel normal storage allocation failed");
            var kernel=Fn<Kernel>(lib,"boom_java_unsafe_memory");int calls=0;
            Func<int,ulong> call=op=>{Reset(ctx);ulong r=kernel(ctx,args,pool,op);Need(Marshal.ReadInt32(ctx)==0,"Kernel smoke failed op="+op+", kind="+Marshal.ReadInt32(ctx));calls++;return r;};
            ulong cookie=Cookies(pool)(valueField);Arguments(args,receiver,obj,cookie);Need(call(5)==0,"Initial kernel field value differs");
            Arguments(args,receiver,obj,cookie,7);call(21);Arguments(args,receiver,obj,cookie,7,9);Need(call(69)==1,"Kernel CAS failed");
            Need(call(37)==9,"Kernel volatile load differs");Arguments(args,receiver,obj,cookie,5,1);Need(call(85)==9,"Kernel exchange failure witness differs");
            Need(call(5)==9,"Failed exchange changed memory");Need(call(69)==0,"CAS false result differs");
            Arguments(args,receiver,obj,cookie,9,17);Need(call(85)==9&&call(5)==17,"Kernel successful exchange differs");
            IntPtr array=Fn<Alloc>(lib,"boom_heap_alloc")(heap,32,0,266);Need(array!=IntPtr.Zero,"Memory kernel array fixture failed");
            Arguments(args,receiver,array,4,99);call(53);Need(call(37)==99,"Kernel array volatile access differs");
            Arguments(args,receiver,array,1,0x12345678);call(21);Need(call(5)==0x12345678,"Kernel unaligned plain byte view differs");
            return calls;
        }finally{if(heap!=IntPtr.Zero)Need(destroy(heap)==1,"Memory kernel fixture heap cleanup failed");for(int i=memory.Count-1;i>=0;i--)Marshal.FreeHGlobal(memory[i]);if(dll!=IntPtr.Zero)NativeLibrary.Free(dll);NativeLibrary.Free(lib);}
    }
}
