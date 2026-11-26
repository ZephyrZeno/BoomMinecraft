// Executes AOT fixture methods on native-created OS threads. Original Thread
// constructors, currentThread/start0 Java bindings and live stack maps are absent.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

public static class BoomThreadRegistryProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {public uint Kind,PC,Method,Depth;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string path,IntPtr zero,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr CreateEventW(IntPtr security,bool manual,bool state,string name);
    [DllImport("kernel32.dll")] static extern bool SetEvent(IntPtr handle);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr handle,uint milliseconds);
    [DllImport("kernel32.dll")] static extern uint GetCurrentThreadId();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapCreate(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int HeapDestroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Allocate(IntPtr heap,ulong bytes,uint refs,uint tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context context,[In] ulong[] arguments);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr StaticRoots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint TraceRelease();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(IntPtr heap,uint maxRecords);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint End(IntPtr registry);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong NextId(IntPtr registry);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Current(IntPtr registry);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Attach(IntPtr registry,IntPtr root,ulong id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl,SetLastError=true)] delegate IntPtr Start(IntPtr registry,IntPtr config);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Join(IntPtr registry,IntPtr record,uint timeout);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release(IntPtr registry,IntPtr record);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Result(IntPtr registry,IntPtr record,IntPtr output);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Roots(IntPtr registry,IntPtr buffer,uint capacity,out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr pool,IntPtr entry,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr pool);
    static void Check(bool value,string message){if(!value)throw new Exception(message);}
    static void Until(Func<bool> ready,string message){long limit=Environment.TickCount64+15000;while(!ready()){Check(Environment.TickCount64<limit,message);Thread.Sleep(1);}}
    static T Fn<T>(IntPtr module,string name){IntPtr p=GetProcAddress(module,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static IntPtr Open(string path){IntPtr m=LoadLibraryExW(path,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Module load failed: "+path);return m;}
    static IntPtr Zero(int bytes){IntPtr p=Marshal.AllocHGlobal(bytes);for(int i=0;i<bytes;i+=8)Marshal.WriteInt64(p,i,0);return p;}
    static ulong Bits(IntPtr p){return unchecked((ulong)p.ToInt64());}
    static long Read64(BinaryReader b){byte[] v=b.ReadBytes(8);Check(v.Length==8,"Truncated oracle");if(BitConverter.IsLittleEndian)Array.Reverse(v);return BitConverter.ToInt64(v,0);}
    static uint Read32(BinaryReader b){byte[] v=b.ReadBytes(4);Check(v.Length==4,"Truncated oracle");if(BitConverter.IsLittleEndian)Array.Reverse(v);return BitConverter.ToUInt32(v,0);}
    static ulong Call(IntPtr module,params ulong[] args){var c=new Context();ulong value=Fn<Entry>(module,"boom_entry")(ref c,args);Check(c.Kind==0&&c.Depth==0,"AOT producer/summary failed: "+c.Kind);return value;}
    static int Reachable(List<IntPtr> roots){var seen=new HashSet<IntPtr>();var todo=new Stack<IntPtr>(roots);while(todo.Count!=0){IntPtr p=todo.Pop();if(p==IntPtr.Zero||!seen.Add(p))continue;uint flags=unchecked((uint)Marshal.ReadInt32(p,-24)),refs=unchecked((uint)Marshal.ReadInt32(p,-20));long bytes=Marshal.ReadInt64(p,-16);Check((flags&0xfffffffd)==0xb00b0001&&bytes>=0&&refs<=(ulong)bytes/8&&seen.Count<1048576,"Invalid thread/static root graph");for(int i=0;i<refs;i++)todo.Push(Marshal.ReadIntPtr(p,i*8));}return seen.Count;}
    static void GC(IntPtr runtime,IntPtr heap,IntPtr[] modules,IntPtr threadRoots,uint count){
        var roots=new List<IntPtr>();for(int i=0;i<count;i++)roots.Add(Marshal.ReadIntPtr(threadRoots,i*8));
        foreach(IntPtr m in modules){IntPtr p=Fn<StaticRoots>(m,"boom_get_static_roots")(out uint n);for(int i=0;i<n;i++)roots.Add(Marshal.ReadIntPtr(p,i*8));}
        IntPtr all=Zero(Math.Max(8,roots.Count*8));try{for(int i=0;i<roots.Count;i++)Marshal.WriteIntPtr(all,i*8,roots[i]);int live=Reachable(roots);Check(Fn<Collect>(runtime,"boom_heap_collect")(heap,all,(uint)roots.Count)!=ulong.MaxValue&&Marshal.ReadInt64(heap,56)==live,"Native thread roots lost objects during quiescent GC");}finally{Marshal.FreeHGlobal(all);}
    }
    static void Configure(IntPtr config,IntPtr adapter,IntPtr info,IntPtr root,ulong id){
        Marshal.WriteInt32(config,0,0x5453504e);Marshal.WriteInt32(config,4,1);Marshal.WriteIntPtr(config,8,root);Marshal.WriteInt64(config,16,unchecked((long)id));
        Marshal.WriteIntPtr(config,24,GetProcAddress(adapter,"boom_thread_test_main"));Marshal.WriteIntPtr(config,32,GetProcAddress(adapter,"boom_thread_test_exit"));Marshal.WriteIntPtr(config,40,GetProcAddress(adapter,"boom_thread_test_failure"));Marshal.WriteIntPtr(config,48,info);Marshal.WriteInt64(config,56,0);
    }
    // Raw VM publication storage only: these fixtures are not original Threads.
    static void ConfigurePublication(IntPtr config,IntPtr adapter,IntPtr info,IntPtr root,ulong id){
        Configure(config,adapter,info,root,id);
        Marshal.WriteInt32(config,4,2);
        Marshal.WriteIntPtr(config,24,GetProcAddress(adapter,"boom_thread_test_publication_main"));
        Marshal.WriteIntPtr(config,32,GetProcAddress(adapter,"boom_thread_test_publication_exit"));
        Marshal.WriteIntPtr(config,40,GetProcAddress(adapter,"boom_thread_test_publication_failure"));
        Marshal.WriteIntPtr(config,56,GetProcAddress(adapter,"boom_thread_test_publish"));
        Marshal.WriteIntPtr(config,64,GetProcAddress(adapter,"boom_thread_test_rollback"));
        Marshal.WriteInt64(config,72,0);Marshal.WriteInt64(config,80,0);
    }
    public static uint RunPublication(string runtime,string adapter){
        IntPtr r=Open(runtime),a=Open(adapter),heap=IntPtr.Zero,registry=IntPtr.Zero;
        IntPtr info=Zero(64),config=Zero(88),output=Zero(64),roots=Zero(8);
        var records=new List<IntPtr>();var objects=new List<IntPtr>();bool allJoined=true;
        var create=Fn<Create>(r,"boom_threads_create");var destroy=Fn<End>(r,"boom_threads_destroy");
        var next=Fn<NextId>(r,"boom_threads_next_id");var start=Fn<Start>(r,"boom_threads_start");
        var join=Fn<Join>(r,"boom_threads_join");var release=Fn<Release>(r,"boom_threads_release");
        var result=Fn<Result>(r,"boom_threads_result");var allocate=Fn<Allocate>(r,"boom_heap_alloc");
        var rootBegin=Fn<Roots>(r,"boom_threads_roots");var rootEnd=Fn<End>(r,"boom_threads_roots_end");
        try{
            heap=Fn<HeapCreate>(r,"boom_heap_create")(1024*1024);Check(heap!=IntPtr.Zero,"Publication heap creation failed");
            registry=create(heap,128);Check(registry!=IntPtr.Zero,"Publication registry creation failed");
            Marshal.WriteIntPtr(info,0,registry);
            IntPtr failedRoot=allocate(heap,16,0,265);Check(failedRoot!=IntPtr.Zero,"Publication fixture allocation failed");
            ConfigurePublication(config,a,info,failedRoot,next(registry));
            foreach(int offset in new[]{56,64,80}){
                long saved=Marshal.ReadInt64(config,offset);Marshal.WriteInt64(config,offset,offset==80?1:0);
                Check(start(registry,config)==IntPtr.Zero&&Marshal.ReadInt64(info,8)==0,"Malformed Start88 published state: "+offset);
                Marshal.WriteInt64(config,offset,saved);
            }
            // An impossible SIZE_T stack reservation makes the real OS call fail.
            // STACK_SIZE_PARAM_IS_A_RESERVATION prevents a large commit request.
            Marshal.WriteInt64(config,72,-1);
            IntPtr failed=start(registry,config);int error=Marshal.GetLastWin32Error();
            if(failed!=IntPtr.Zero)records.Add(failed);
            Check(failed==IntPtr.Zero&&error!=0,"Impossible stack reservation unexpectedly started a worker");
            Check(Marshal.ReadInt64(info,8)==1&&Marshal.ReadInt64(info,32)==1&&Marshal.ReadInt64(info,16)==0&&
                  Marshal.ReadIntPtr(failedRoot)==IntPtr.Zero&&Marshal.ReadInt64(failedRoot,8)==0,
                  "CreateThread failure did not roll back published peer/state");
            Check(rootBegin(registry,roots,1,out uint n)==0&&n==0&&rootEnd(registry)==0,"Failed spawn retained a registry record");
            const int batches=8,jobs=64;
            for(int batch=0;batch<batches;batch++){
                objects.Clear();
                for(int i=0;i<jobs;i++){
                    IntPtr obj=allocate(heap,16,0,265);Check(obj!=IntPtr.Zero,"Publication object allocation failed");
                    objects.Add(obj);ConfigurePublication(config,a,info,obj,next(registry));
                    if((i&1)!=0)Marshal.WriteInt64(config,72,1024*1024);
                    IntPtr token=start(registry,config);Check(token!=IntPtr.Zero,"Published worker failed to start");records.Add(token);
                }
                for(int i=0;i<jobs;i++){
                    IntPtr token=records[i];Check(join(registry,token,15000)==0,"Published worker did not join");
                    Check(result(registry,token,output)==0&&Marshal.ReadInt32(output,8)==0&&
                          Marshal.ReadInt32(output,40)==0&&Marshal.ReadInt32(output,44)==0&&Marshal.ReadInt32(output,60)==4,
                          "Published worker observed an invalid peer, state or current identity");
                    Check(Marshal.ReadIntPtr(objects[i])==IntPtr.Zero&&Marshal.ReadInt64(objects[i],8)==2,"Exit did not clear the published peer");
                    Check(release(registry,token)==0,"Published worker record did not release");
                }
                records.Clear();
            }
            Check(Marshal.ReadInt64(info,8)==batches*jobs+1&&Marshal.ReadInt64(info,16)==batches*jobs&&
                  Marshal.ReadInt64(info,24)==0&&Marshal.ReadInt64(info,32)==1&&Marshal.ReadInt64(info,40)==batches*jobs,
                  "Publication/rollback/worker/exit counts differ");
            Check(destroy(registry)==0,"Publication registry did not clean up");registry=IntPtr.Zero;
            return batches*jobs;
        }finally{
            if(registry!=IntPtr.Zero){
                foreach(IntPtr token in records){if(join(registry,token,30000)==0)release(registry,token);else allJoined=false;}
                if(allJoined&&destroy(registry)!=0)allJoined=false;
            }
            if(allJoined){
                if(heap!=IntPtr.Zero)Check(Fn<HeapDestroy>(r,"boom_heap_destroy")(heap)!=0,"Publication heap cleanup failed");
                foreach(IntPtr p in new[]{info,config,output,roots})Marshal.FreeHGlobal(p);
                FreeLibrary(a);FreeLibrary(r);
            }
        }
    }
    public static void Run(string runtime,string adapter,string image,int resultOffset,int checkOffset,string oracle){
        Check(resultOffset>=0&&checkOffset>=0&&resultOffset<4096&&checkOffset<4096,"Invalid fixture field offsets");IntPtr r=Open(runtime),a=Open(adapter),heap=IntPtr.Zero,registry=IntPtr.Zero,pool=IntPtr.Zero;
        IntPtr info=Zero(112),config=Zero(64),output=Zero(64),roots=Zero(4096*8),input=IntPtr.Zero,poolOutput=IntPtr.Zero;
        IntPtr entered=CreateEventW(IntPtr.Zero,true,false,null),gate=CreateEventW(IntPtr.Zero,true,false,null);bool frozen=false,allJoined=true;
        var modules=new IntPtr[1];var records=new List<IntPtr>();var objects=new IntPtr[64];
        var create=Fn<Create>(r,"boom_threads_create");var destroy=Fn<End>(r,"boom_threads_destroy");var next=Fn<NextId>(r,"boom_threads_next_id");var current=Fn<Current>(r,"boom_threads_current");var attach=Fn<Attach>(r,"boom_threads_attach");var detach=Fn<End>(r,"boom_threads_detach");var start=Fn<Start>(r,"boom_threads_start");var join=Fn<Join>(r,"boom_threads_join");var release=Fn<Release>(r,"boom_threads_release");var result=Fn<Result>(r,"boom_threads_result");var rootBegin=Fn<Roots>(r,"boom_threads_roots");var rootEnd=Fn<End>(r,"boom_threads_roots_end");
        try {
            heap=Fn<HeapCreate>(r,"boom_heap_create")(4*1024*1024);Check(heap!=IntPtr.Zero&&entered!=IntPtr.Zero&&gate!=IntPtr.Zero,"Thread test setup failed");
            for(int i=0;i<1;i++){modules[i]=Open(image);Check(Fn<Bind>(modules[i],"boom_bind_heap")(heap)==1,"AOT thread workload bind failed");}
            Check(create(IntPtr.Zero,128)==IntPtr.Zero&&create(heap,0)==IntPtr.Zero&&create(heap,16385)==IntPtr.Zero,"Bad thread registry config accepted");
            registry=create(heap,128);Check(registry!=IntPtr.Zero&&create(heap,128)==IntPtr.Zero,"Registry singleton failed");Marshal.WriteIntPtr(info,0,registry);
            Marshal.WriteIntPtr(info,8,GetProcAddress(modules[0],"boom_entry"));Marshal.WriteIntPtr(info,16,GetProcAddress(modules[0],"boom_entry"));Marshal.WriteIntPtr(info,24,GetProcAddress(modules[0],"boom_entry"));Marshal.WriteInt32(info,96,resultOffset);Marshal.WriteIntPtr(info,64,entered);Marshal.WriteIntPtr(info,72,gate);
            IntPtr idAddress=Fn<Current>(r,"boom_threads_id_address")(registry);Check(idAddress!=IntPtr.Zero&&(idAddress.ToInt64()&7)==0&&Marshal.ReadInt64(idAddress)==2,"Thread ID address/reservation failed");
            IntPtr main=new IntPtr(unchecked((long)Call(modules[0],0,0,uint.MaxValue,1)));Check(current(registry)==IntPtr.Zero,"Unattached thread returned an object");
            Check(attach(registry,main,1)!=IntPtr.Zero&&current(registry)==main,"Primordial thread attachment failed");
            Check(attach(registry,main,1)==IntPtr.Zero&&destroy(registry)==170,"Duplicate attachment/destroy accepted");
            Marshal.WriteInt64(roots,0,0x12345678);Check(rootBegin(registry,roots,4096,out uint n)==170&&n==0&&Marshal.ReadInt64(roots)==0x12345678,"Active/external thread roots were declared quiescent");
            Check(detach(registry)==0&&current(registry)==IntPtr.Zero&&detach(registry)==87&&attach(registry,main,1)==IntPtr.Zero,"Primordial detach/ID reservation failed");
            Check(attach(registry,IntPtr.Zero,2)==IntPtr.Zero&&attach(registry,new IntPtr(1),2)==IntPtr.Zero,"Invalid root attached");
            const int jobs=2049;pool=Fn<PoolCreate>(r,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"ID pool failed");input=Zero(jobs*128);poolOutput=Zero(jobs*32);for(int i=0;i<jobs;i++)Marshal.WriteIntPtr(input,i*128,registry);
            var ids=new HashSet<ulong>();for(int batch=0;batch<3;batch++){Check(Fn<PoolRun>(r,"boom_pool_run")(pool,GetProcAddress(a,"boom_thread_test_id_job"),input,poolOutput,jobs)==0,"ID pool run failed");for(int i=0;i<jobs;i++){ulong id=unchecked((ulong)Marshal.ReadInt64(poolOutput,i*32));Check(id>=2&&id<6149&&ids.Add(id)&&Marshal.ReadInt64(poolOutput,i*32+8)==0&&Marshal.ReadInt64(poolOutput,i*32+16)==0&&Marshal.ReadInt64(poolOutput,i*32+24)==0,"Concurrent Java ID duplicated/corrupted context");}}
            Check(ids.Count==6147&&Marshal.ReadInt64(idAddress)==6149,"VM/native shared ID counter differs");Check(Fn<PoolDestroy>(r,"boom_pool_destroy")(pool)==0,"ID workers did not join");pool=IntPtr.Zero;
            Marshal.WriteInt64(idAddress,long.MaxValue);Check(next(registry)==0&&Marshal.ReadInt64(idAddress)==long.MaxValue,"ID counter overflow was accepted");Marshal.WriteInt64(idAddress,6149);
            IntPtr autoObject=new IntPtr(unchecked((long)Call(modules[0],0,0,7,1)));ulong autoId=next(registry);Exception autoFailure=null;
            var external=new Thread(()=>{try{Check(attach(registry,autoObject,autoId)!=IntPtr.Zero&&current(registry)==autoObject,"External thread attachment failed");}catch(Exception e){autoFailure=e;}});external.Start();Check(external.Join(15000),"External thread did not exit");if(autoFailure!=null)throw autoFailure;
            Until(()=>{uint code=rootBegin(registry,roots,4096,out uint count);if(code==0){Check(count==0,"Exited external thread remained rooted");Check(rootEnd(registry)==0,"External cleanup root lease failed");return true;}Check(code==170,"External cleanup root query failed");return false;},"FLS automatic external detach failed");
            for(int i=0;i<64;i++)objects[i]=new IntPtr(unchecked((long)Call(modules[0],0,0,(uint)i,i%9==0?0UL:(ulong)(i%7+1))));
            Configure(config,a,info,objects[0],next(registry));
            foreach(int offset in new[]{0,4,8,16,24,32,40,56}){long saved=Marshal.ReadInt64(config,offset);Marshal.WriteInt64(config,offset,offset<8?7:offset==56?1:0);Check(start(registry,config)==IntPtr.Zero,"Invalid spawn config accepted: "+offset);Marshal.WriteInt64(config,offset,saved);}
            IntPtr foreign=Fn<HeapCreate>(r,"boom_heap_create")(65536);try{IntPtr p=Fn<Allocate>(r,"boom_heap_alloc")(foreign,32,0,265);Marshal.WriteIntPtr(config,8,p);Check(start(registry,config)==IntPtr.Zero,"Foreign heap root accepted");Marshal.WriteIntPtr(config,8,objects[0]);}finally{Check(Fn<HeapDestroy>(r,"boom_heap_destroy")(foreign)!=0,"Foreign heap cleanup failed");}
            var nativeIds=new ulong[64];
            for(int i=0;i<64;i++){nativeIds[i]=next(registry);Configure(config,a,info,objects[i],nativeIds[i]);IntPtr token=start(registry,config);Check(token!=IntPtr.Zero,"Native AOT task start failed: "+i);records.Add(token);}
            Check(WaitForSingleObject(entered,10000)==0,"Native task entry did not run");
            Check(rootBegin(registry,roots,4096,out n)==170&&n==0&&destroy(registry)==170&&release(registry,records[0])==170&&result(registry,records[0],output)==170&&join(registry,records[0],0)==258,"Active native task lifetime/GC gate failed");
            Configure(config,a,info,objects[0],next(registry));Check(start(registry,config)==IntPtr.Zero,"Duplicate live task object was accepted");
            SetEvent(gate);foreach(IntPtr token in records)Check(join(registry,token,15000)==0,"Native task did not join");
            using(var binary=new BinaryReader(File.OpenRead(oracle))){Check(binary.BaseStream.Length==64*20,"Thread oracle size differs");for(int i=0;i<64;i++){long value=Read64(binary);uint kind=Read32(binary);long summary=Read64(binary);uint status=result(registry,records[i],output);Check(status==0&&Marshal.ReadInt64(output)==value&&unchecked((uint)Marshal.ReadInt32(output,8))==kind&&Marshal.ReadInt32(output,20)==0&&unchecked((ulong)Marshal.ReadInt64(output,48))==nativeIds[i]&&Marshal.ReadInt32(output,60)==4&&unchecked((uint)Marshal.ReadInt32(output,56))!=GetCurrentThreadId(),"Native AOT task result/context/identity differs: "+i+" status="+status+" result="+Marshal.ReadInt64(output)+" expected="+value+" kind="+Marshal.ReadInt32(output,8)+" expectedKind="+kind+" depth="+Marshal.ReadInt32(output,20)+" id="+Marshal.ReadInt64(output,48)+" expectedId="+nativeIds[i]+" state="+Marshal.ReadInt32(output,60)+" callback="+Marshal.ReadInt32(output,40)+" exit="+Marshal.ReadInt32(output,44));Call(modules[0],4,Bits(objects[i]),0,0);Check(Marshal.ReadInt64(objects[i],checkOffset)==summary,"AOT failure/exit/summary differs from JVM: "+i);}}
            Check(Marshal.ReadInt64(info,32)==64&&Marshal.ReadInt64(info,40)==8&&Marshal.ReadInt64(info,48)==64&&Marshal.ReadInt64(info,56)==0&&Marshal.ReadInt64(info,80)==0,"Native callback lifecycle/current-thread/FP differs");
            Marshal.WriteInt64(roots,0,0x12345678);Check(rootBegin(registry,roots,0,out n)==122&&n==0&&Marshal.ReadInt64(roots)==0x12345678,"Small root buffer partially published");
            Marshal.WriteIntPtr(records[0],112,new IntPtr(1));Check(rootBegin(registry,roots,4096,out n)==87&&n==0,"Malformed pending root accepted");Marshal.WriteIntPtr(records[0],112,IntPtr.Zero);
            Marshal.WriteIntPtr(records[0],112,objects[1]);Check(rootBegin(registry,roots,4096,out n)==0&&n==65,"Completed thread/pending roots missing");frozen=true;
            Check(rootBegin(registry,roots,4096,out uint ignored)==170&&ignored==0&&destroy(registry)==170&&release(registry,records[0])==170,"Frozen registry accepted mutation");
            Check(Task.Run(()=>rootEnd(registry)).Result==5,"Another thread ended the GC lease");
            Configure(config,a,info,main,next(registry));Check(start(registry,config)==IntPtr.Zero&&attach(registry,main,next(registry))==IntPtr.Zero,"New mutator entered a frozen VM");
            GC(r,heap,modules,roots,n);Check(rootEnd(registry)==0,"GC root lease did not end");frozen=false;Marshal.WriteIntPtr(records[0],112,IntPtr.Zero);
            foreach(IntPtr token in records)Check(release(registry,token)==0,"Completed native task did not release");records.Clear();
            Check(rootBegin(registry,roots,4096,out n)==0&&n==0,"Released records retained roots");frozen=true;GC(r,heap,modules,roots,n);Check(rootEnd(registry)==0,"Empty GC lease failed");frozen=false;
            Marshal.WriteInt32(info,100,3);IntPtr failedObject=new IntPtr(unchecked((long)Call(modules[0],0,0,0,0)));Configure(config,a,info,failedObject,next(registry));IntPtr failed=start(registry,config);Check(failed!=IntPtr.Zero,"Callback status test did not start");records.Add(failed);
            Check(join(registry,failed,15000)==0&&result(registry,failed,output)==0&&Marshal.ReadInt32(output,8)==1&&Marshal.ReadInt32(output,40)==12345&&Marshal.ReadInt32(output,44)==54321,"Uncaught/exit callback errors were discarded");
            Check(release(registry,failed)==0,"Callback status record did not release");records.Clear();Marshal.WriteInt32(info,100,0);
            Marshal.WriteInt32(info,88,1);IntPtr abruptObject=new IntPtr(unchecked((long)Call(modules[0],0,0,99,1)));Configure(config,a,info,abruptObject,next(registry));IntPtr abrupt=start(registry,config);Check(abrupt!=IntPtr.Zero,"Abnormal exit test did not start");records.Add(abrupt);
            Check(join(registry,abrupt,15000)==0&&result(registry,abrupt,output)==0&&Marshal.ReadInt32(output,60)==5&&Marshal.ReadInt32(output,8)==7&&Marshal.ReadInt32(output,40)==574&&Marshal.ReadInt64(info,48)==65,"Abrupt OS exit was reported as a successful Java exit");
            Check(release(registry,abrupt)==0,"Abnormal record release failed");records.Clear();
            Check(destroy(registry)==0,"Registry did not destroy quiescently");IntPtr old=registry;registry=IntPtr.Zero;Check(current(old)==IntPtr.Zero&&next(old)==0&&destroy(old)==87,"Destroyed registry accepted work");
        } finally {
            SetEvent(gate);
            if(registry!=IntPtr.Zero){if(frozen)rootEnd(registry);foreach(IntPtr token in records){if(join(registry,token,30000)==0)release(registry,token);else allJoined=false;}detach(registry);if(allJoined&&destroy(registry)!=0)allJoined=false;}
            if(pool!=IntPtr.Zero)Fn<PoolDestroy>(r,"boom_pool_destroy")(pool);
            if(allJoined){foreach(IntPtr m in modules)if(m!=IntPtr.Zero){IntPtr p=GetProcAddress(m,"boom_release_trace_pool");if(p!=IntPtr.Zero)Check(Marshal.GetDelegateForFunctionPointer<TraceRelease>(p)()==0,"Guest frames still active");FreeLibrary(m);}if(heap!=IntPtr.Zero)Check(Fn<HeapDestroy>(r,"boom_heap_destroy")(heap)!=0,"Native thread heap cleanup failed");foreach(IntPtr p in new[]{info,config,output,roots,input,poolOutput})if(p!=IntPtr.Zero)Marshal.FreeHGlobal(p);CloseHandle(entered);CloseHandle(gate);FreeLibrary(a);FreeLibrary(r);}
        }
    }
}
