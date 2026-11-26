using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

// Explicit metadata/TLS fixtures. Original Java method execution is tested separately.
public static class BoomNormalCallerProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Enter(IntPtr pool,IntPtr node,IntPtr row,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Leave(IntPtr pool,IntPtr node,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Head(IntPtr pool,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Release(IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Caller(IntPtr ctx,IntPtr argv,IntPtr pool,uint op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Probe(ulong a,ulong b,ulong c,ulong d);
    static T Fn<T>(IntPtr lib,string name) where T:Delegate {return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(lib,name));}
    static void Need(bool ok,string why) {if(!ok)throw new Exception(why);}
    static IntPtr Alloc(List<IntPtr> list,int bytes) {var p=Marshal.AllocHGlobal(bytes);for(int i=0;i<bytes;i++)Marshal.WriteByte(p,i,0);list.Add(p);return p;}
    static void Reset(IntPtr c) {for(int i=0;i<32;i+=8)Marshal.WriteInt64(c,i,0);}
    static IntPtr Row(IntPtr rows,int i) {return IntPtr.Add(rows,32*i);}
    static IntPtr Node(IntPtr nodes,int i) {return IntPtr.Add(nodes,48*i);}
    static void Push(Enter enter,IntPtr p,IntPtr n,IntPtr r,IntPtr c) {Marshal.WriteInt32(c,12,Marshal.ReadInt32(c,12)+1);Need(enter(p,n,r,c)==0,"Trace enter failed: "+Marshal.ReadInt32(c));}
    static void Pop(Leave leave,IntPtr p,IntPtr n,IntPtr c) {Need(leave(p,n,c)==0,"Trace leave failed");Marshal.WriteInt32(c,12,Marshal.ReadInt32(c,12)-1);}
    public static long[] Run(string runtime,string fixture) {
        var lib=NativeLibrary.Load(runtime);var dll=NativeLibrary.Load(fixture);var memory=new List<IntPtr>();
        IntPtr trace=IntPtr.Zero,legacy=IntPtr.Zero;Release release=null;
        try {
            var enter=Fn<Enter>(lib,"boom_trace_enter");var leave=Fn<Leave>(lib,"boom_trace_leave");
            var head=Fn<Head>(lib,"boom_trace_head");release=Fn<Release>(lib,"boom_trace_release");
            var caller=Fn<Caller>(lib,"boom_java_caller_type");
            IntPtr rows=Alloc(memory,8*32),types=Alloc(memory,8*32),records=Alloc(memory,8*48),classes=Alloc(memory,64);
            trace=Alloc(memory,48);var pool=Alloc(memory,64);var ctx=Alloc(memory,32);var nodes=Alloc(memory,8*48);
            for(int i=0;i<8;i++) {
                IntPtr row=Row(rows,i),type=IntPtr.Add(types,i*32);
                Marshal.WriteInt32(row,0,1000+i);Marshal.WriteIntPtr(row,8,type);Marshal.WriteInt32(row,16,i==0?0:1);Marshal.WriteInt32(row,20,i);
                Marshal.WriteIntPtr(records,i*48,type);
            }
            Marshal.WriteInt32(Row(rows,0),4,40);Marshal.WriteInt32(Row(rows,1),4,8);
            Marshal.WriteInt32(Row(rows,3),4,64);Marshal.WriteInt32(Row(rows,4),4,16);Marshal.WriteInt32(Row(rows,6),4,64);
            Marshal.WriteInt32(classes,0,0x4a434c53);Marshal.WriteInt32(classes,4,1);Marshal.WriteInt32(classes,12,8);Marshal.WriteIntPtr(classes,24,records);
            Marshal.WriteInt32(trace,0,0x5452504c);Marshal.WriteInt32(trace,4,3);Marshal.WriteInt32(trace,12,-1);Marshal.WriteInt32(trace,16,8);Marshal.WriteIntPtr(trace,24,rows);
            Marshal.WriteInt32(pool,0,0x4a434352);Marshal.WriteInt32(pool,4,1);Marshal.WriteIntPtr(pool,8,classes);Marshal.WriteIntPtr(pool,16,trace);
            Marshal.WriteInt32(pool,24,1000);Marshal.WriteInt32(pool,28,0);Marshal.WriteInt32(pool,32,32);Marshal.WriteInt32(pool,36,32);
            int checks=0;
            Need(caller(ctx,IntPtr.Zero,pool,0)==uint.MaxValue&&Marshal.ReadInt32(ctx)==0,"Empty chain not null");checks++;
            Push(enter,trace,Node(nodes,2),Row(rows,2),ctx);Push(enter,trace,Node(nodes,1),Row(rows,1),ctx);Push(enter,trace,Node(nodes,0),Row(rows,0),ctx);
            Need(caller(ctx,IntPtr.Zero,pool,0)==2&&head(trace,ctx)==nodes,"Actual TLS chain ignored");checks++;
            Need(release(trace)==170&&Marshal.ReadInt64(trace,32)==1,"Active outer lease not retained");checks++;
            Marshal.WriteInt32(ctx,66);Need(caller(ctx,IntPtr.Zero,pool,0)==uint.MaxValue&&Marshal.ReadInt32(ctx)==66,"Pending error overwritten");checks++;
            ResetError(ctx);
            foreach(int offset in new[]{0,4,32,36,40,48,56}) {
                long old=Marshal.ReadInt64(pool,offset);Marshal.WriteInt32(pool,offset,123);
                Need(caller(ctx,IntPtr.Zero,pool,0)==uint.MaxValue&&Marshal.ReadInt32(ctx)==7,"Bad caller pool accepted: "+offset);checks++;
                Marshal.WriteInt64(pool,offset,old);ResetError(ctx);
            }
            Marshal.WriteInt32(Row(rows,1),4,0);Need(caller(ctx,IntPtr.Zero,pool,0)==uint.MaxValue&&Marshal.ReadInt32(ctx)==23,"Non-caller-sensitive immediate caller accepted");checks++;
            Marshal.WriteInt32(Row(rows,1),4,8);ResetError(ctx);
            foreach(int mode in new[]{0,1,2,3}) {
                if(mode==0)Marshal.WriteInt32(Node(nodes,2),24,1);
                if(mode==1)Marshal.WriteInt32(Node(nodes,0),24,1);
                if(mode==2)Marshal.WriteInt32(Row(rows,2),20,8);
                if(mode==3)Marshal.WriteInt64(Row(rows,2),24,1);
                Need(caller(ctx,IntPtr.Zero,pool,0)==uint.MaxValue&&Marshal.ReadInt32(ctx)==7,"Corrupt frame accepted: "+mode);checks++;
                Marshal.WriteInt32(Node(nodes,2),24,0);Marshal.WriteInt32(Node(nodes,0),24,0);Marshal.WriteInt32(Row(rows,2),20,2);Marshal.WriteInt64(Row(rows,2),24,0);ResetError(ctx);
            }
            Marshal.WriteInt32(Row(rows,0),0,2000);Need(caller(ctx,IntPtr.Zero,pool,0)==uint.MaxValue&&Marshal.ReadInt32(ctx)==23,"Wrong native getter accepted");checks++;Marshal.WriteInt32(Row(rows,0),0,1000);ResetError(ctx);
            Pop(leave,trace,Node(nodes,0),ctx);Pop(leave,trace,Node(nodes,1),ctx);Pop(leave,trace,Node(nodes,2),ctx);
            Need(head(trace,ctx)==IntPtr.Zero&&Marshal.ReadInt64(trace,32)==0&&Marshal.ReadInt32(ctx,12)==0,"Returned frame retained");checks++;
            foreach(int i in new[]{2,4,3,1,0})Push(enter,trace,Node(nodes,i),Row(rows,i),ctx);
            Need(caller(ctx,IntPtr.Zero,pool,0)==4,"Hidden frame incorrectly treated as security-ignored");checks++;
            foreach(int i in new[]{0,1,3,4,2})Pop(leave,trace,Node(nodes,i),ctx);
            foreach(int i in new[]{2,3,6,1,0})Push(enter,trace,Node(nodes,i),Row(rows,i),ctx);
            Need(caller(ctx,IntPtr.Zero,pool,0)==2,"Security-ignored frames not skipped");checks++;
            foreach(int i in new[]{0,1,6,3,2})Pop(leave,trace,Node(nodes,i),ctx);
            var nested=Alloc(memory,32);Push(enter,trace,Node(nodes,2),Row(rows,2),ctx);
            Push(enter,trace,Node(nodes,1),Row(rows,1),nested);Push(enter,trace,Node(nodes,0),Row(rows,0),nested);
            Need(caller(nested,IntPtr.Zero,pool,0)==uint.MaxValue&&Marshal.ReadInt32(nested)==0,"Cross-Context embedding boundary crossed");checks++;
            Pop(leave,trace,Node(nodes,0),nested);Pop(leave,trace,Node(nodes,1),nested);Pop(leave,trace,Node(nodes,2),ctx);
            foreach(int mode in new[]{0,1,2,3,4,5}) {
                IntPtr row=Row(rows,5);Marshal.WriteInt32(row,4,0);Marshal.WriteInt32(row,16,1);Marshal.WriteInt64(row,24,0);
                if(mode==0)Marshal.WriteInt32(row,4,256);
                if(mode==1)Marshal.WriteInt32(row,16,0);
                if(mode==2)Marshal.WriteInt32(row,16,65536);
                if(mode==3)Marshal.WriteInt32(row,4,32);
                if(mode==4)Marshal.WriteInt64(row,24,1);
                if(mode==5)Marshal.WriteInt32(row,4,128);
                Marshal.WriteInt32(ctx,12,1);Need(enter(trace,Node(nodes,5),row,ctx)==1&&Marshal.ReadInt32(ctx)==(mode==5?20:7),"Invalid trace row accepted: "+mode);checks++;Reset(ctx);
            }
            Need(enter(trace,Node(nodes,5),IntPtr.Add(rows,1),ctx)==1&&Marshal.ReadInt32(ctx)==7,"Unaligned method row accepted");checks++;Reset(ctx);
            const int workers=8,iterations=1024;
            using(var barrier=new Barrier(workers)) {
                var tasks=new Task[workers];
                for(int w=0;w<workers;w++)tasks[w]=Task.Factory.StartNew(()=>{
                    var owned=new List<IntPtr>();var c=Alloc(owned,32);var ns=Alloc(owned,144);
                    try {barrier.SignalAndWait();for(int k=0;k<iterations;k++) {
                        for(int i=2;i>=0;i--)Push(enter,trace,Node(ns,i),Row(rows,i),c);
                        Need(caller(c,IntPtr.Zero,pool,0)==2&&Marshal.ReadInt32(c)==0,"Concurrent TLS caller mixed across threads");
                        for(int i=0;i<3;i++)Pop(leave,trace,Node(ns,i),c);
                        Need(head(trace,c)==IntPtr.Zero,"Concurrent chain leaked");
                    }}finally{foreach(var p in owned)Marshal.FreeHGlobal(p);}
                },CancellationToken.None,TaskCreationOptions.LongRunning,TaskScheduler.Default);
                Task.WaitAll(tasks);
            }
            Need(Marshal.ReadInt64(trace,32)==0&&release(trace)==0&&release(trace)==0,"Quiescent TLS slot not released");checks++;
            legacy=Alloc(memory,48);var legacyRow=Alloc(memory,32);
            Marshal.WriteInt32(legacy,0,0x5452504c);Marshal.WriteInt32(legacy,4,2);Marshal.WriteInt32(legacy,12,-1);Marshal.WriteInt32(legacy,16,1);Marshal.WriteIntPtr(legacy,24,legacyRow);
            Marshal.WriteIntPtr(legacyRow,8,types);Marshal.WriteInt32(legacyRow,16,1);Marshal.WriteInt32(legacyRow,20,123);Marshal.WriteInt64(legacyRow,24,456);
            Push(enter,legacy,Node(nodes,0),legacyRow,ctx);Need(head(legacy,ctx)==nodes,"Legacy ABI2 lost");Pop(leave,legacy,nodes,ctx);Need(release(legacy)==0,"Legacy slot leaked");checks++;
            var probe=Fn<Probe>(dll,"boom_test_large_stack");long probes=0;
            foreach(ulong x in new ulong[]{0,1,0x100000000,ulong.MaxValue,0x123456789abcdef0})for(int i=0;i<128;i++) {
                ulong b=unchecked(x+1),c=unchecked(x+3),d=unchecked(x+7),expected=unchecked(65576+x+b+c+d);
                Need(probe(x,b,c,d)==expected,"Stack probing changed RAX/argument registers");probes++;
            }
            return new long[]{checks,workers*iterations,workers,probes};
        } finally {
            if(release!=null)foreach(var p in new[]{trace,legacy})if(p!=IntPtr.Zero)Need(release(p)==0,"Live fixture trace pool at unload");
            foreach(var p in memory)Marshal.FreeHGlobal(p);NativeLibrary.Free(dll);NativeLibrary.Free(lib);
        }
    }
    static void ResetError(IntPtr c) {Marshal.WriteInt32(c,0);}
}
