// Direct ABI/lifetime test only. Original Unsafe/ThreadIdentifiers execution is
// verified separately; these tests do not impersonate constructed Java threads.
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
public static class BoomVmThreadIdMemoryProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Heap(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int One(IntPtr value);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(IntPtr heap,int max);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Memory(IntPtr ctx,IntPtr argv,int action,IntPtr heap);
    static T Fn<T>(IntPtr m,string n)where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(m,n));}
    static void Need(bool v,string m){if(!v)throw new Exception(m);}
    static void Clear(IntPtr p,int n){for(int i=0;i<n;i+=8)Marshal.WriteInt64(p,i,0);}
    public static long[] Run(string path){
        var dll=NativeLibrary.Load(path);var make=Fn<Heap>(dll,"boom_heap_create");var free=Fn<One>(dll,"boom_heap_destroy");
        var create=Fn<Create>(dll,"boom_threads_create");var destroy=Fn<One>(dll,"boom_threads_destroy");var access=Fn<Memory>(dll,"boom_threads_id_memory");
        var heap=make(4UL*1024*1024);var other=make(4UL*1024*1024);IntPtr reg=IntPtr.Zero;
        var ctx=Marshal.AllocHGlobal(32);var argv=Marshal.AllocHGlobal(40);int checks=0;
        try{
            Need(heap!=IntPtr.Zero&&other!=IntPtr.Zero,"VM counter test heaps failed");Clear(ctx,32);Clear(argv,40);
            Need(access(ctx,argv,2,heap)==0&&Marshal.ReadInt32(ctx)==20,"Counter access without a live registry succeeded");checks++;
            reg=create(heap,64);Need(reg!=IntPtr.Zero,"VM counter registry creation failed");long address=reg.ToInt64()+32;Marshal.WriteInt64(argv,16,address);
            Clear(ctx,32);Need(access(ctx,argv,2,heap)==2&&Marshal.ReadInt32(ctx)==0,"Reserved primordial ID/counter differs");
            Marshal.WriteInt64(argv,24,2);Marshal.WriteInt64(argv,32,3);Need(access(ctx,argv,4,heap)==1&&access(ctx,argv,0,heap)==3,"Counter CAS success/load differs");
            Need(access(ctx,argv,4,heap)==0&&access(ctx,argv,0,heap)==3,"Failed counter CAS modified memory");
            Marshal.WriteInt64(argv,24,3);Marshal.WriteInt64(argv,32,4);Need(access(ctx,argv,5,heap)==3,"Counter exchange old value differs");
            Need(access(ctx,argv,5,heap)==4&&access(ctx,argv,0,heap)==4,"Failed counter exchange old value differs");
            foreach(int action in new[]{1,3,6,-1}){Clear(ctx,32);Need(access(ctx,argv,action,heap)==0&&Marshal.ReadInt32(ctx)==20,"Unsupported VM counter operation succeeded");checks++;}
            foreach(long bad in new[]{0L,address-8,address+1,address+8,heap.ToInt64()}){Clear(ctx,32);Marshal.WriteInt64(argv,16,bad);Need(access(ctx,argv,2,heap)==0&&Marshal.ReadInt32(ctx)==20,"Non-counter or unaligned address was dereferenced");checks++;}
            Marshal.WriteInt64(argv,16,address);Clear(ctx,32);Need(access(ctx,argv,2,other)==0&&Marshal.ReadInt32(ctx)==20,"Foreign heap reached the VM counter");checks++;
            Marshal.WriteInt64(argv,8,heap.ToInt64());Clear(ctx,32);Need(access(ctx,argv,2,heap)==0&&Marshal.ReadInt32(ctx)==20,"Non-NULL base was accepted by the counter-only ABI");checks++;Marshal.WriteInt64(argv,8,0);
            Clear(ctx,32);Need(access(ctx,IntPtr.Zero,2,heap)==0&&Marshal.ReadInt32(ctx)==20,"NULL counter argv was accepted");checks++;
            Need(access(IntPtr.Zero,argv,2,heap)==0,"NULL context was dereferenced");checks++;
            Clear(ctx,32);Marshal.WriteInt32(ctx,9);Marshal.WriteInt32(ctx,4,123);Marshal.WriteInt32(ctx,8,456);Marshal.WriteInt32(ctx,12,7);Marshal.WriteInt64(ctx,16,789);Marshal.WriteInt64(ctx,24,1011);
            Need(access(ctx,argv,4,heap)==0&&Marshal.ReadInt32(ctx)==9&&Marshal.ReadInt32(ctx,4)==123&&Marshal.ReadInt32(ctx,8)==456&&Marshal.ReadInt32(ctx,12)==7&&Marshal.ReadInt64(ctx,16)==789&&Marshal.ReadInt64(ctx,24)==1011,"Counter service changed a pending Context32");checks++;
            const int workers=8,iterations=4096;var tasks=new Task[workers];var values=new long[workers*iterations];using var gate=new Barrier(workers);
            for(int w=0;w<workers;w++){int slot=w;tasks[w]=Task.Factory.StartNew(()=>{var c=Marshal.AllocHGlobal(32);var a=Marshal.AllocHGlobal(40);try{Clear(a,40);Marshal.WriteInt64(a,16,address);gate.SignalAndWait();for(int i=0;i<iterations;i++){
                for(;;){Clear(c,32);long old=access(c,a,2,heap);Need(Marshal.ReadInt32(c)==0,"Concurrent counter load failed");Marshal.WriteInt64(a,24,old);Marshal.WriteInt64(a,32,old+1);long ok=access(c,a,4,heap);Need(Marshal.ReadInt32(c)==0,"Concurrent counter CAS failed");if(ok==1){values[slot*iterations+i]=old;break;}}
            }}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}},TaskCreationOptions.LongRunning);}
            Task.WaitAll(tasks);Array.Sort(values);for(int i=0;i<values.Length;i++)Need(values[i]==i+4,"Concurrent counter increments lost or duplicated an ID");
            Clear(ctx,32);Need(access(ctx,argv,2,heap)==values.Length+4,"Final VM counter value differs");
            long expected=values.Length+4;int stop=0;using var started=new CountdownEvent(workers);
            for(int w=0;w<workers;w++){tasks[w]=Task.Factory.StartNew(()=>{var c=Marshal.AllocHGlobal(32);var a=Marshal.AllocHGlobal(40);try{Clear(a,40);Marshal.WriteInt64(a,16,address);started.Signal();while(Volatile.Read(ref stop)==0){Clear(c,32);long value=access(c,a,2,heap);int kind=Marshal.ReadInt32(c);Need((kind==0&&value==expected)||(kind==20&&value==0),"Registry destruction raced an unchecked counter dereference");}for(int i=0;i<512;i++){Clear(c,32);Need(access(c,a,2,heap)==0&&Marshal.ReadInt32(c)==20,"Destroyed VM counter address remained usable");}}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}},TaskCreationOptions.LongRunning);}
            started.Wait();Need(destroy(reg)==0,"Registry destruction under counter readers failed");reg=IntPtr.Zero;Volatile.Write(ref stop,1);Task.WaitAll(tasks);
            return new long[]{workers,values.Length,checks,workers*512};
        }finally{if(reg!=IntPtr.Zero)Need(destroy(reg)==0,"Counter registry test cleanup failed");Marshal.FreeHGlobal(ctx);Marshal.FreeHGlobal(argv);Need(free(other)==1&&free(heap)==1,"Counter test heap cleanup failed");NativeLibrary.Free(dll);}
    }
}
