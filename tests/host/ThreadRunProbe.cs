// Test host only: VM storage is prepared here; original Thread Java methods and
// Runnable bodies execute the AOT assembly. This does not execute Thread.<init>.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
public static class BoomThreadRunProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {public uint Kind,PC,Method,Depth;public ulong Pending,Plan;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Indexed(uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(uint c,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr NewObject(IntPtr h,IntPtr layout,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr RegCreate(IntPtr h,uint max);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Attach(IntPtr r,IntPtr obj,ulong id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Next(IntPtr r);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Get();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Native(ref Context c,[In] ulong[] args,IntPtr pool,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();
    static void Check(bool ok,string msg){if(!ok)throw new Exception(msg);}
    static IntPtr Open(string p){IntPtr m=LoadLibraryExW(p,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Thread run load failed");return m;}
    static T Fn<T>(IntPtr m,string name){IntPtr p=GetProcAddress(m,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static ulong Bits(IntPtr p){return unchecked((ulong)p.ToInt64());}
    static IntPtr Object(IntPtr m,IntPtr heap,uint id){var c=new Context();IntPtr p=Fn<NewObject>(m,"boom_object_new")(heap,Fn<Indexed>(m,"boom_get_object_layout")(id),ref c);Check(p!=IntPtr.Zero&&c.Kind==0,"VM thread storage allocation failed");return p;}
    static IntPtr Call(Entry fn,uint mode,IntPtr thread,IntPtr task,int value=0,int divisor=1){var c=new Context();ulong v=fn(ref c,new[]{(ulong)mode,Bits(thread),Bits(task),unchecked((ulong)value),unchecked((ulong)divisor)});Check(c.Kind==0&&c.Depth==0,"Thread.run error "+c.Kind+" pc "+c.PC+" method "+c.Method);return new IntPtr(unchecked((long)v));}
    static uint U32(BinaryReader r){uint v=0;for(int i=0;i<4;i++)v=(v<<8)|r.ReadByte();return v;}
    static long I64(BinaryReader r){ulong v=0;for(int i=0;i<8;i++)v=(v<<8)|r.ReadByte();return unchecked((long)v);}
    static void GC(IntPtr m,IntPtr heap,List<IntPtr> extras){IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n);var all=new List<IntPtr>(extras);for(int i=0;i<n;i++)all.Add(Marshal.ReadIntPtr(roots,i*8));var seen=new HashSet<IntPtr>();var todo=new Stack<IntPtr>(all);while(todo.Count>0){IntPtr p=todo.Pop();if(p==IntPtr.Zero||!seen.Add(p))continue;uint count=unchecked((uint)Marshal.ReadInt32(p,-20));for(uint i=0;i<count;i++)todo.Push(Marshal.ReadIntPtr(p,checked((int)i*8)));}IntPtr buffer=Marshal.AllocHGlobal(all.Count*8);try{for(int i=0;i<all.Count;i++)Marshal.WriteIntPtr(buffer,i*8,all[i]);Check(Fn<Collect>(m,"boom_heap_collect")(heap,buffer,(uint)all.Count)!=ulong.MaxValue,"Thread run GC failed");Check((ulong)Marshal.ReadInt64(heap,56)==(ulong)seen.Count,"Thread run independent root graph differs");}finally{Marshal.FreeHGlobal(buffer);}}
    // IDs: Thread,FieldHolder,ArithmeticException,Reference,SharedSecrets.
    // Offsets: Thread.holder,Thread.scopedValueBindings,FieldHolder.task,
    // Task.value,divisor,sum,calls,failures,matched.
    public static void Run(string image,string runtime,string oracle,uint[] ids,int[] offsets,uint accessField){
        IntPtr m=Open(image),r=Open(runtime),heap=IntPtr.Zero,registry=IntPtr.Zero;bool attached=false;
        try{
            heap=Fn<Create>(r,"boom_heap_create")(2097152);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Thread run heap bind failed");
            registry=Fn<RegCreate>(m,"boom_threads_create")(heap,64);Check(registry!=IntPtr.Zero&&Fn<One>(m,"boom_bind_thread_registry")(registry)==0,"Thread run registry bind failed");
            var entry=Fn<Entry>(m,"boom_entry32");IntPtr main=Object(m,heap,ids[0]),mainHolder=Object(m,heap,ids[1]);Marshal.WriteIntPtr(main,offsets[0],mainHolder);
            Check(Fn<Attach>(m,"boom_threads_attach")(registry,main,1)!=IntPtr.Zero,"Main VM view attach failed");attached=true;
            Call(entry,0,main,IntPtr.Zero);Check(Marshal.ReadInt32(Fn<Indexed>(m,"boom_get_class_descriptor")(ids[3]),8)==0,"Reference initializer was not cold");
            var threadRoots=new List<IntPtr>();object gate=new object();Exception error=null;var workers=new Thread[8];
            for(int w=0;w<8;w++){int worker=w;workers[w]=new Thread(()=>{bool bound=false;try{
                IntPtr t=Object(m,heap,ids[0]),holder=Object(m,heap,ids[1]);Marshal.WriteIntPtr(t,offsets[0],holder);
                ulong id=Fn<Next>(m,"boom_threads_next_id")(registry);Check(Fn<Attach>(m,"boom_threads_attach")(registry,t,id)!=IntPtr.Zero,"Worker VM view attach failed");bound=true;
                IntPtr task=Call(entry,0,t,IntPtr.Zero,worker+1,worker%3+1);Marshal.WriteIntPtr(holder,offsets[2],task);Marshal.WriteIntPtr(t,offsets[1],task);
                int calls=0;for(int i=worker;i<6147;i+=8){Check(Call(entry,1,t,task)==task,"Runnable return identity changed");calls++;}
                long increment=unchecked(((long)(worker+1)*6364136223846793005L+1442695040888963407L)/(worker%3+1));
                Check(Marshal.ReadInt64(task,offsets[5])==unchecked(increment*calls)&&Marshal.ReadInt32(task,offsets[6])==calls&&Marshal.ReadByte(task,offsets[8])==1,"Concurrent original Thread.run result differs");
                lock(gate){threadRoots.Add(t);}
            }catch(Exception e){lock(gate){error=error??e;}}finally{if(bound)Check(Fn<One>(m,"boom_threads_detach")(registry)==0,"Worker VM view detach failed");}});workers[w].Start();}
            foreach(Thread t in workers)t.Join();if(error!=null)throw error;
            Check(Marshal.ReadInt32(Fn<Indexed>(m,"boom_get_class_descriptor")(ids[3]),8)==2,"Original Reference initialization did not execute");
            Check(Marshal.ReadIntPtr(Fn<Field>(m,"boom_get_static_field")(ids[4],accessField))!=IntPtr.Zero,"Original Reference access object was not published");
            IntPtr target=Object(m,heap,ids[0]),targetHolder=Object(m,heap,ids[1]);Marshal.WriteIntPtr(target,offsets[0],targetHolder);
            using(var reader=new BinaryReader(File.OpenRead(oracle)))for(int i=0;i<512;i++){
                int value=unchecked((int)U32(reader)),divisor=unchecked((int)U32(reader));long sum=I64(reader);int calls=unchecked((int)U32(reader)),failures=unchecked((int)U32(reader));byte matched=reader.ReadByte();
                IntPtr task=Call(entry,0,main,IntPtr.Zero,value,divisor);Marshal.WriteIntPtr(targetHolder,offsets[2],task);Marshal.WriteIntPtr(main,offsets[1],i%2==0?task:IntPtr.Zero);
                Check(Call(entry,2,target,task)==task&&Marshal.ReadInt64(task,offsets[5])==sum&&Marshal.ReadInt32(task,offsets[6])==calls&&Marshal.ReadInt32(task,offsets[7])==failures&&Marshal.ReadByte(task,offsets[8])==matched,"Original Thread.run JVM mismatch "+i);
            }
            Check(Call(entry,1,main,IntPtr.Zero)==IntPtr.Zero,"Null Runnable should be a normal return");
            IntPtr failing=Call(entry,0,main,IntPtr.Zero,17,0);Marshal.WriteIntPtr(targetHolder,offsets[2],failing);var thrown=new Context();entry(ref thrown,new[]{1UL,Bits(target),Bits(failing),0UL,0UL});Check(thrown.Kind==16&&thrown.Pending!=0&&thrown.Depth==0&&Marshal.ReadIntPtr(new IntPtr(unchecked((long)thrown.Pending)),-8)==Fn<Indexed>(m,"boom_get_object_layout")(ids[2]),"Thread.run did not propagate ArithmeticException: kind="+thrown.Kind+" pending="+thrown.Pending+" depth="+thrown.Depth);
            var native=Fn<Native>(m,"boom_thread_native_dispatch");IntPtr pool=Fn<Get>(m,"boom_get_thread_native_pool")();foreach(IntPtr value in new[]{IntPtr.Zero,main,failing}){var c=new Context();Check(native(ref c,new[]{Bits(value)},pool,17)==0&&c.Kind==0,"Native escape rejected a materialized value");}
            IntPtr other=Fn<Create>(r,"boom_heap_create")(65536);try{IntPtr foreign=Object(m,other,ids[0]);var c=new Context();native(ref c,new[]{Bits(foreign)},pool,17);Check(c.Kind==7,"Native escape accepted a foreign heap");}finally{Fn<One>(r,"boom_heap_destroy")(other);}
            var pending=new Context{Kind=9,PC=17,Method=23,Pending=99};native(ref pending,Array.Empty<ulong>(),pool,17);Check(pending.Kind==9&&pending.PC==17&&pending.Method==23&&pending.Pending==99,"Native escape overwrote a pending exception");
            Check(Fn<One>(m,"boom_threads_detach")(registry)==0,"Main VM view detach failed");attached=false;
            threadRoots.Add(main);threadRoots.Add(target);GC(m,heap,threadRoots);
            Check(Fn<One>(m,"boom_bind_thread_registry")(IntPtr.Zero)==0&&Fn<One>(m,"boom_threads_destroy")(registry)==0,"Thread run registry shutdown failed");registry=IntPtr.Zero;
        }finally{if(attached)Fn<One>(m,"boom_threads_detach")(registry);if(registry!=IntPtr.Zero){Fn<One>(m,"boom_bind_thread_registry")(IntPtr.Zero);Fn<One>(m,"boom_threads_destroy")(registry);}IntPtr p=GetProcAddress(m,"boom_release_trace_pool");if(p!=IntPtr.Zero)Check(Marshal.GetDelegateForFunctionPointer<Release>(p)()==0,"Thread run frames remain active");if(heap!=IntPtr.Zero)Check(Fn<One>(r,"boom_heap_destroy")(heap)!=0,"Thread run heap cleanup failed");FreeLibrary(m);FreeLibrary(r);}
    }
}
