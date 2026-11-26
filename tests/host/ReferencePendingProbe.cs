// Development host for the assembly queue kernel, not a Java execution runtime.
using System;
using System.Runtime.InteropServices;
using System.Threading;

public static class BoomReferencePendingProbe {
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapCreate(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int HeapDestroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Allocate(IntPtr h,ulong bytes,uint refs,uint tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Contains(IntPtr h,IntPtr o);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate long Collect(IntPtr h,IntPtr spans,ulong count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Op(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Stopping(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Publish(IntPtr p,IntPtr head);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Get(IntPtr p,out IntPtr head);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Has(IntPtr p,out uint value);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Roots(IntPtr p,IntPtr span);
    static void Check(bool b,string s){if(!b)throw new Exception(s);}
    static T Fn<T>(IntPtr m,string n){var p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static IntPtr Open(string p){var h=LoadLibraryExW(p,IntPtr.Zero,0x1100);Check(h!=IntPtr.Zero,"Cannot load "+p);return h;}
    public static void Run(string runtime,string core){
        var r=Open(runtime);var m=Open(core);
        var create=Fn<Create>(m,"boom_reference_pending_create");var publish=Fn<Publish>(m,"boom_reference_pending_publish");
        var get=Fn<Get>(m,"boom_reference_pending_get");var has=Fn<Has>(m,"boom_reference_pending_has");
        var wait=Fn<Op>(m,"boom_reference_pending_wait");var stop=Fn<Op>(m,"boom_reference_pending_stop");
        var stopping=Fn<Stopping>(m,"boom_reference_pending_stopping");var destroy=Fn<Op>(m,"boom_reference_pending_destroy");
        var roots=Fn<Roots>(m,"boom_reference_pending_roots_begin");var rootsEnd=Fn<Op>(m,"boom_reference_pending_roots_end");
        var heapCreate=Fn<HeapCreate>(r,"boom_heap_create");var heapDestroy=Fn<HeapDestroy>(r,"boom_heap_destroy");
        var allocate=Fn<Allocate>(r,"boom_heap_alloc");var contains=Fn<Contains>(r,"boom_heap_contains");
        IntPtr heap=IntPtr.Zero,otherHeap=IntPtr.Zero,pool=IntPtr.Zero,otherPool=IntPtr.Zero;
        IntPtr span=Marshal.AllocHGlobal(16);Thread worker=null;Thread[] many=null;bool leased=false;
        uint workerStatus=uint.MaxValue;Exception workerError=null;
        try {
            Check(create(IntPtr.Zero)==IntPtr.Zero,"Null heap accepted");
            uint present;IntPtr value;
            foreach(var bad in new[]{IntPtr.Zero,new IntPtr(0x12340)}){
                Check(has(bad,out present)==87&&present==0,"Unknown pool dereferenced");
                Check(get(bad,out value)==87&&value==IntPtr.Zero,"Unknown pool get accepted");
                Check(wait(bad)==87&&stop(bad)==87&&destroy(bad)==87&&rootsEnd(bad)==87&&stopping(bad)==-1,"Unknown pool operation accepted");
            }
            heap=heapCreate(1048576);otherHeap=heapCreate(1048576);Check(heap!=IntPtr.Zero&&otherHeap!=IntPtr.Zero,"Heap creation failed");
            var head=allocate(heap,16,1,265);var child=allocate(heap,16,0,265);var garbage=allocate(heap,16,0,265);
            var foreign=allocate(otherHeap,16,0,265);Check(head!=IntPtr.Zero&&child!=IntPtr.Zero&&garbage!=IntPtr.Zero&&foreign!=IntPtr.Zero,"VM storage allocation failed");
            Marshal.WriteIntPtr(head,0,child);
            pool=create(heap);otherPool=create(otherHeap);Check(pool!=IntPtr.Zero&&otherPool!=IntPtr.Zero,"Pool creation failed");
            Check(publish(pool,IntPtr.Zero)==87&&publish(pool,foreign)==87,"Foreign or null head accepted");
            Check(has(pool,out present)==0&&present==0&&get(pool,out value)==0&&value==IntPtr.Zero,"New queue not empty");
            Check(destroy(pool)==170,"Running pool destroyed without shutdown");

            worker=new Thread(()=>{try{workerStatus=wait(pool);}catch(Exception ex){workerError=ex;}});worker.Start();
            Check(SpinWait.SpinUntil(()=>Marshal.ReadInt32(pool,48)==1,10000),"Worker never entered native wait");
            Check(!worker.Join(80),"Empty queue returned from blocking wait");
            Check(roots(pool,span)==170&&destroy(pool)==170,"Active wait failed to protect roots/lifetime");
            Check(publish(pool,head)==0,"Pending batch publication failed");
            Check(worker.Join(10000)&&workerError==null&&workerStatus==0,"Publication failed to wake waiter");worker=null;
            Check(has(pool,out present)==0&&present==1,"Wait consumed the batch");
            Check(publish(pool,head)==170,"Existing batch was overwritten");

            Check(roots(pool,span)==0,"Root lease failed");leased=true;
            Check(Marshal.ReadInt64(span,8)==1&&Marshal.ReadIntPtr(Marshal.ReadIntPtr(span))==head,"Root span does not contain pending head");
            Check(publish(pool,head)==170&&get(pool,out value)==170&&has(pool,out present)==170&&wait(pool)==170&&stop(pool)==170&&destroy(pool)==170,"Root lease allowed queue mutation or destruction");
            uint wrongOwner=0;worker=new Thread(()=>wrongOwner=rootsEnd(pool));worker.Start();Check(worker.Join(10000)&&wrongOwner==87,"Root lease released by another OS thread");worker=null;
            var collected=Fn<Collect>(r,"boom_heap_collect_spans")(heap,span,1);
            Check(collected==1&&contains(heap,head)==1&&contains(heap,child)==1&&contains(heap,garbage)==0,"Pending root graph was lost or garbage retained");
            Check(rootsEnd(pool)==0,"Root lease owner release failed");leased=false;
            Check(get(pool,out value)==0&&value==head&&has(pool,out present)==0&&present==0,"Get did not atomically clear pending head");

            for(int i=0;i<128;i++){
                workerStatus=uint.MaxValue;workerError=null;
                if((i&1)==0)Check(publish(pool,head)==0,"Publish-before-wait failed");
                worker=new Thread(()=>{try{workerStatus=wait(pool);}catch(Exception ex){workerError=ex;}});worker.Start();
                if((i&1)!=0){Check(SpinWait.SpinUntil(()=>Marshal.ReadInt32(pool,48)==1,10000),"Waiter not registered");Check(publish(pool,head)==0,"Publish-during-wait failed");}
                Check(worker.Join(10000)&&workerError==null&&workerStatus==0,"Lost pending wake");worker=null;
                Check(get(pool,out value)==0&&value==head,"Batch lost after wake");
            }
            var statuses=new uint[8];many=new Thread[8];using(var gate=new ManualResetEventSlim(false)){
                for(int i=0;i<many.Length;i++){int n=i;many[i]=new Thread(()=>{gate.Wait();statuses[n]=publish(pool,head);});many[i].Start();}
                gate.Set();foreach(var t in many)Check(t.Join(10000),"Publisher still active");many=null;
            }
            int winners=0;foreach(var status in statuses){if(status==0)winners++;else Check(status==170,"Invalid concurrent publication status");}
            Check(winners==1&&get(pool,out value)==0&&value==head,"Concurrent publishers lost/overwrote batch");

            statuses=new uint[16];many=new Thread[16];
            for(int i=0;i<many.Length;i++){int n=i;many[i]=new Thread(()=>statuses[n]=wait(pool));many[i].Start();}
            Check(SpinWait.SpinUntil(()=>Marshal.ReadInt32(pool,48)==16,10000),"Shutdown waiters not registered");
            Check(stop(pool)==0&&stop(pool)==0&&stopping(pool)==1,"Shutdown request failed");
            foreach(var t in many)Check(t.Join(10000),"Shutdown failed to wake a waiter");many=null;
            foreach(var status in statuses)Check(status==995,"Shutdown was reported as normal pending work");
            Check(Marshal.ReadInt32(pool,48)==0,"Waiters leaked");
            Check(get(pool,out value)==995&&value==IntPtr.Zero&&has(pool,out present)==995&&present==0&&publish(pool,head)==995,"Stopped queue still processed work");
            Check(stopping(otherPool)==0&&publish(otherPool,foreign)==0,"Stopping one pool affected another");
            var dead=pool;Check(destroy(pool)==0,"Stopped pool cleanup failed");pool=IntPtr.Zero;
            Check(get(dead,out value)==87&&stop(dead)==87&&destroy(dead)==87,"Released pool remained registered");
            Check(stop(otherPool)==0&&destroy(otherPool)==0,"Independent pool cleanup failed");otherPool=IntPtr.Zero;
            Check(heapDestroy(heap)==1,"Heap cleanup failed");heap=IntPtr.Zero;
            Check(heapDestroy(otherHeap)==1,"Second heap cleanup failed");otherHeap=IntPtr.Zero;
        } finally {
            if(leased){Check(rootsEnd(pool)==0,"Lease teardown failed");leased=false;}
            if(pool!=IntPtr.Zero)Check(stop(pool)==0,"Stop during teardown failed");
            if(worker!=null)Check(worker.Join(15000),"Kernel test worker still running");
            if(many!=null)foreach(var t in many)if(t!=null)Check(t.Join(15000),"Kernel test workers still running");
            if(pool!=IntPtr.Zero)Check(destroy(pool)==0,"Pool teardown failed");
            if(otherPool!=IntPtr.Zero){Check(stop(otherPool)==0,"Other stop teardown failed");Check(destroy(otherPool)==0,"Other pool teardown failed");}
            if(heap!=IntPtr.Zero)Check(heapDestroy(heap)==1,"Heap teardown failed");
            if(otherHeap!=IntPtr.Zero)Check(heapDestroy(otherHeap)==1,"Other heap teardown failed");
            Marshal.FreeHGlobal(span);FreeLibrary(m);FreeLibrary(r);
        }
    }
}
