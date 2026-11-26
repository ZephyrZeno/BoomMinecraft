// FFI, VM preconstructor peer fixtures and assertions; all guest services are ASM.
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading.Tasks;
public static class BoomNormalThreadSourceProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapCreate(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int HeapDestroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int BindHeap(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr state,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr New(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Contains(IntPtr heap,IntPtr oop);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(IntPtr heap,int capacity);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr registry);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Attach(IntPtr registry,IntPtr oop,long id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Detach(IntPtr registry);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long NextId(IntPtr registry);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr registry);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Entry(IntPtr ctx,IntPtr args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Release();
    static T Fn<T>(IntPtr dll,string name)where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(dll,name));}
    static void Need(bool value,string message){if(!value)throw new Exception(message);}
    static void Reset(IntPtr p){for(int i=0;i<32;i+=8)Marshal.WriteInt64(p,i,0);}
    public static long[] Run(string configuration){
        using var doc=JsonDocument.Parse(File.ReadAllText(configuration));var s=doc.RootElement;
        var runtime=NativeLibrary.Load(s.GetProperty("runtime").GetString());var image=NativeLibrary.Load(s.GetProperty("image").GetString());
        IntPtr heap=IntPtr.Zero,registry=IntPtr.Zero;bool attached=false,bound=false,success=false;
        var ctx=Marshal.AllocHGlobal(32);var args=Marshal.AllocHGlobal(16);
        var detach=Fn<Detach>(runtime,"boom_threads_detach");var bind=Fn<Bind>(image,"boom_provider_thread_bind");
        try{
            Reset(ctx);Marshal.WriteInt64(args,0);Marshal.WriteInt64(args,8,0);heap=Fn<HeapCreate>(runtime,"boom_heap_create")(128UL*1024*1024);
            Need(heap!=IntPtr.Zero&&Fn<BindHeap>(image,"boom_java_string_literals_bind_heap")(heap)==1,"Normal Thread heap bind failed");
            var ensure=Fn<Ensure>(runtime,"boom_class_ensure32");
            foreach(var root in s.GetProperty("roots").EnumerateArray())Need(ensure(NativeLibrary.GetExport(image,"boom_class"+root.GetInt32()),ctx)==0&&Marshal.ReadInt32(ctx)==0,"Original Thread prerequisite failed");
            int thread=s.GetProperty("metadata").GetProperty("thread_class").GetInt32();var state=NativeLibrary.GetExport(image,"boom_class"+thread);
            Need(Marshal.ReadInt32(state,8)==0,"Original Thread was already initialized");
            var entries=new Entry[6];for(int i=0;i<6;i++)entries[i]=Fn<Entry>(image,s.GetProperty("native_symbols").GetProperty(i.ToString()).GetString());
            const int workers=8,registrations=1024,iterations=512;
            Parallel.For(0,workers,w=>{var c=Marshal.AllocHGlobal(32);var a=Marshal.AllocHGlobal(16);try{for(int i=0;i<registrations;i++){Reset(c);Marshal.WriteInt64(a,0);Need(entries[0](c,a)==0&&Marshal.ReadInt32(c)==0,"Concurrent original Thread registration failed: kind="+Marshal.ReadInt32(c)+" method="+Marshal.ReadInt32(c,8)+" pc="+Marshal.ReadInt32(c,4));}}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});
            var pool=NativeLibrary.GetExport(image,"boom_provider_thread_pool");
            Need(Marshal.ReadInt32(state,8)==2&&Marshal.ReadInt32(pool,8)==2,"Original Thread initializer or registration did not complete");
            var table=Marshal.ReadIntPtr(pool,16);for(int i=0;i<18;i++)Need(Marshal.ReadIntPtr(table,16+i*32+16)==NativeLibrary.GetExport(runtime,"boom_thread_native_"+i),"Thread table target is an import thunk instead of the canonical runtime export");
            foreach(var field in s.GetProperty("static_fields").EnumerateObject()){
                var oop=Marshal.ReadIntPtr(NativeLibrary.GetExport(image,field.Value.GetString()));Need(oop!=IntPtr.Zero&&Fn<Contains>(runtime,"boom_heap_contains")(heap,oop)==1,"Original Thread initializer did not publish "+field.Name);
                if(field.Name=="EMPTY_STACK_TRACE")Need(Marshal.ReadInt64(oop,-16)==0,"Original empty stack trace array differs");
            }
            int errors=0;Reset(ctx);Need(entries[2](ctx,args)==0&&Marshal.ReadInt32(ctx)==7,"Unbound VM thread lookup was accepted");errors++;
            registry=Fn<Create>(runtime,"boom_threads_create")(heap,64);Need(registry!=IntPtr.Zero&&bind(registry)==0,"Normal Thread registry bind failed");bound=true;
            var make=Fn<New>(runtime,"boom_object_new");Reset(ctx);var raw=make(heap,Marshal.ReadIntPtr(pool,24),ctx);Need(raw!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"VM preconstructor Thread allocation failed");
            for(int i=0;i<Marshal.ReadInt64(raw,-16);i++)Need(Marshal.ReadByte(raw,i)==0,"VM preconstructor Thread fields were prepopulated");
            var attach=Fn<Attach>(runtime,"boom_threads_attach");Need(attach(registry,raw,1)!=IntPtr.Zero,"VM primordial peer attach failed");attached=true;
            Reset(ctx);Need(entries[1](ctx,args)==raw.ToInt64()&&entries[2](ctx,args)==raw.ToInt64()&&Marshal.ReadInt32(ctx)==0,"Normal Thread current/carrier identity differs");
            Need(bind(IntPtr.Zero)==170,"Live primordial peer registry was unbound");errors++;
            Reset(ctx);long address=entries[5](ctx,args);Need(address==registry.ToInt64()+32&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt64(new IntPtr(address))==2,"Source VM ID address or reserved main ID differs");
            Marshal.WriteIntPtr(args,raw);Reset(ctx);Need(entries[3](ctx,args)==0&&Marshal.ReadInt32(ctx)==0,"Heap materialization native failed");Marshal.WriteIntPtr(args,IntPtr.Zero);Need(entries[3](ctx,args)==0&&Marshal.ReadInt32(ctx)==0,"NULL materialization changed");
            Need(entries[4](ctx,args)==0&&Marshal.ReadInt32(ctx)==0,"Original Thread yield failed");
            var peers=new IntPtr[workers];var ids=new long[workers];var next=Fn<NextId>(runtime,"boom_threads_next_id");
            for(int i=0;i<workers;i++){Reset(ctx);peers[i]=make(heap,Marshal.ReadIntPtr(pool,24),ctx);ids[i]=next(registry);Need(peers[i]!=IntPtr.Zero&&ids[i]==i+2&&Marshal.ReadInt32(ctx)==0,"Worker preconstructor peer or ID allocation failed");}
            var tasks=new Task[workers];for(int worker=0;worker<workers;worker++){int w=worker;tasks[w]=Task.Factory.StartNew(()=>{var c=Marshal.AllocHGlobal(32);var a=Marshal.AllocHGlobal(16);bool joined=false;try{Need(attach(registry,peers[w],ids[w])!=IntPtr.Zero,"Worker VM peer attach failed");joined=true;for(int i=0;i<iterations;i++){Reset(c);Marshal.WriteIntPtr(a,peers[w]);Need(entries[0](c,a)==0&&entries[1](c,a)==peers[w].ToInt64()&&entries[2](c,a)==peers[w].ToInt64()&&entries[3](c,a)==0&&entries[4](c,a)==0&&entries[5](c,a)==address&&Marshal.ReadInt32(c)==0,"Concurrent normal Thread native identity/query failed");}}finally{if(joined)Need(detach(registry)==0,"Worker VM peer detach failed");Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}},TaskCreationOptions.LongRunning);}
            Task.WaitAll(tasks);
            Need(detach(registry)==0,"Primordial VM peer detach failed");attached=false;
            Reset(ctx);Need(entries[2](ctx,args)==0&&Marshal.ReadInt32(ctx)==7,"Detached VM thread lookup was accepted");errors++;
            Reset(ctx);Marshal.WriteInt32(ctx,9);Marshal.WriteInt32(ctx,4,123);Marshal.WriteInt32(ctx,8,456);Marshal.WriteInt32(ctx,12,7);Need(entries[2](ctx,args)==0&&Marshal.ReadInt32(ctx)==9&&Marshal.ReadInt32(ctx,4)==123&&Marshal.ReadInt32(ctx,8)==456&&Marshal.ReadInt32(ctx,12)==7,"Thread native changed pending Context32");errors++;
            Need(bind(IntPtr.Zero)==0,"Quiescent Thread registry did not unbind");bound=false;
            Need(Fn<Destroy>(runtime,"boom_threads_destroy")(registry)==0,"Thread registry destruction failed");registry=IntPtr.Zero;
            Need(Marshal.ReadInt32(NativeLibrary.GetExport(image,"boom_diagnostic_pool"),8)==0,"Original Thread initializer reached an unavailable dependency");
            success=true;return new long[]{workers,workers*registrations,18,workers,workers*iterations*6,errors};
        }finally{
            if(attached)Need(detach(registry)==0,"VM peer cleanup detach failed");
            if(bound)Need(bind(IntPtr.Zero)==0,"Thread registry cleanup unbind failed");
            if(registry!=IntPtr.Zero)Need(Fn<Destroy>(runtime,"boom_threads_destroy")(registry)==0,"Thread registry cleanup destroy failed");
            if(success)Need(Fn<Release>(image,"boom_release_trace_pool")()==0,"Thread source retained Java frames");
            if(heap!=IntPtr.Zero){int status=Fn<HeapDestroy>(runtime,"boom_heap_destroy")(heap);if(success)Need(status==1,"Thread source heap cleanup failed");}
            Marshal.FreeHGlobal(args);Marshal.FreeHGlobal(ctx);if(success){NativeLibrary.Free(image);NativeLibrary.Free(runtime);}
        }
    }
}
