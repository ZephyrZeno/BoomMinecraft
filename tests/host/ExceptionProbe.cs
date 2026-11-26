// Development host only. Throwable state and table matching execute in MASM.
using System;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
public static class BoomExceptionProbe {
    [StructLayout(LayoutKind.Sequential)] public struct Context32 { public uint Kind,PC,Method,Depth; public IntPtr Pending; public ulong Reserved; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Allocate(IntPtr heap,ulong bytes,uint refs,IntPtr tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Set(ref Context32 ctx,IntPtr value,IntPtr map,IntPtr throwable);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Match(ref Context32 ctx,uint pc,IntPtr table);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Take(ref Context32 ctx);
    static T Symbol<T>(IntPtr module,string name){IntPtr p=GetProcAddress(module,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static void Check(bool pass,string message){if(!pass)throw new Exception(message);}
    static Context32 Fresh(){return new Context32{PC=1627,Method=17,Depth=3,Reserved=0xfedcba9876543210UL};}
    static void Origin(Context32 ctx){Check(ctx.PC==1627&&ctx.Method==17&&ctx.Depth==3&&ctx.Reserved==0xfedcba9876543210UL,"Origin/depth/tail was overwritten");}
    static IntPtr At(IntPtr value,int offset){return IntPtr.Add(value,offset);}
    static void Row(IntPtr rows,int index,int start,int end,int handler,IntPtr type){IntPtr p=At(rows,index*24);Marshal.WriteInt32(p,start);Marshal.WriteInt32(p,4,end);Marshal.WriteInt32(p,8,handler);Marshal.WriteInt32(p,12,0);Marshal.WriteIntPtr(p,16,type);}
    public static void Run(string path){
        Check(Marshal.SizeOf<Context32>()==32&&Marshal.OffsetOf<Context32>("Pending").ToInt32()==16,"Context32 ABI mismatch");
        IntPtr module=LoadLibraryExW(path,IntPtr.Zero,0x1100),heap=IntPtr.Zero,data=IntPtr.Zero;
        Check(module!=IntPtr.Zero,"Runtime load failed");
        try {
            var create=Symbol<Create>(module,"boom_heap_create");var allocate=Symbol<Allocate>(module,"boom_heap_alloc");
            var collect=Symbol<Collect>(module,"boom_heap_collect");var set=Symbol<Set>(module,"boom_exception_set32");
            var match=Symbol<Match>(module,"boom_exception_match32");var take=Symbol<Take>(module,"boom_exception_take32");
            heap=create(1024*1024);Check(heap!=IntPtr.Zero,"Exception heap failed");
            data=Marshal.AllocHGlobal(2048);Marshal.Copy(new byte[2048],0,data,2048);
            // Probe-only class identities, including a Throwable twin from another loader.
            var types=new IntPtr[7];var values=new IntPtr[7];
            int[] parents={-1,0,1,2,3,1,0};
            for(int i=0;i<types.Length;i++)types[i]=At(data,i*48);
            for(int i=0;i<types.Length;i++){
                IntPtr type=types[i],ancestors=At(data,336+i*56);int count=0;
                for(int parent=parents[i];parent>=0;parent=parents[parent])Marshal.WriteIntPtr(ancestors,count++*8,types[parent]);
                Marshal.WriteInt32(type,0,0x54595045);Marshal.WriteInt32(type,4,1);Marshal.WriteInt32(type,8,1);
                Marshal.WriteIntPtr(type,16,parents[i]<0?IntPtr.Zero:types[parents[i]]);Marshal.WriteIntPtr(type,24,ancestors);Marshal.WriteInt32(type,32,count);
                values[i]=allocate(heap,16,1,new IntPtr(0x501+i));Check(values[i]!=IntPtr.Zero,"Exception object allocation failed");
            }
            IntPtr map=At(data,736),mappingRows=At(data,768),table=At(data,1056),rows=At(data,1104);
            Marshal.WriteInt32(map,0,0x52545950);Marshal.WriteInt32(map,4,1);Marshal.WriteInt32(map,8,7);Marshal.WriteInt32(map,12,7);Marshal.WriteIntPtr(map,16,mappingRows);
            for(int i=0;i<7;i++) {IntPtr row=At(mappingRows,i*40);Marshal.WriteInt64(row,0x501+i);Marshal.WriteIntPtr(row,8,types[i]);Marshal.WriteInt32(row,16,i);Marshal.WriteInt64(row,24,16);Marshal.WriteInt32(row,32,1);}
            Marshal.WriteInt32(table,0,0x45584348);Marshal.WriteInt32(table,4,1);Marshal.WriteInt32(table,8,4);Marshal.WriteIntPtr(table,16,rows);Marshal.WriteIntPtr(table,24,map);Marshal.WriteIntPtr(table,32,types[1]);
            Row(rows,0,10,20,100,types[5]);Row(rows,1,10,20,200,types[2]);Row(rows,2,10,20,300,types[3]);Row(rows,3,10,20,400,IntPtr.Zero);
            var ctx=Fresh();Check(set(ref ctx,values[4],map,types[1])==16&&ctx.Kind==16&&ctx.Pending==values[4],"Pending Throwable was not set");Origin(ctx);
            foreach(uint pc in new uint[]{0,9,20,21,65534})Check(match(ref ctx,pc,table)==0&&ctx.Kind==16&&ctx.Pending==values[4],"Half-open protected range failed");
            foreach(uint pc in new uint[]{10,11,19})Check(match(ref ctx,pc,table)==201&&ctx.Kind==16&&ctx.Pending==values[4],"First assignable catch was not selected");Origin(ctx);
            Row(rows,1,10,20,200,types[3]);Row(rows,2,10,20,300,types[2]);Check(match(ref ctx,15,table)==201,"Handler order was changed");
            Row(rows,0,10,20,0,IntPtr.Zero);Check(match(ref ctx,15,table)==1,"Handler at PC0 or catch-all precedence failed");
            Row(rows,0,10,20,100,types[5]);Row(rows,1,10,20,200,types[2]);Row(rows,2,10,20,300,types[3]);
            IntPtr thrown=take(ref ctx);Check(thrown==values[4]&&ctx.Kind==0&&ctx.PC==0&&ctx.Method==0&&ctx.Pending==IntPtr.Zero&&ctx.Depth==3&&ctx.Reserved==0xfedcba9876543210UL,"Catch did not consume exactly the pending state");
            ctx=Fresh();Check(set(ref ctx,thrown,map,types[1])==16&&match(ref ctx,10,table)==201&&take(ref ctx)==thrown,"Rethrow changed Throwable identity");
            // Reject null/non-Throwable inputs: this service deliberately does not claim
            // to implement Java athrow-null or implicit exception allocation.
            foreach(IntPtr value in new[]{IntPtr.Zero,values[0],values[6]}){ctx=Fresh();set(ref ctx,values[4],map,types[1]);Check(set(ref ctx,value,map,types[1])==7&&ctx.Kind==7&&ctx.Pending==values[4],"Malformed Throwable accepted or existing root lost");}
            ctx=Fresh();set(ref ctx,values[4],map,types[1]);Marshal.WriteInt32(map,4,2);Check(match(ref ctx,15,table)==0&&ctx.Kind==7&&ctx.Pending==values[4],"Map ABI mismatch accepted");Marshal.WriteInt32(map,4,1);
            foreach(int field in new[]{4,12}){ctx=Fresh();set(ref ctx,values[4],map,types[1]);int old=Marshal.ReadInt32(table,field);Marshal.WriteInt32(table,field,2);Check(match(ref ctx,15,table)==0&&ctx.Kind==7&&ctx.Pending==values[4],"Bad table ABI/reserved accepted");Marshal.WriteInt32(table,field,old);}
            foreach(int count in new[]{-1,65536}){ctx=Fresh();set(ref ctx,values[4],map,types[1]);Marshal.WriteInt32(table,8,count);Check(match(ref ctx,15,table)==0&&ctx.Kind==7,"Bad row count accepted");}Marshal.WriteInt32(table,8,4);
            foreach(int field in new[]{0,4,8,12}){ctx=Fresh();set(ref ctx,values[4],map,types[1]);int old=Marshal.ReadInt32(rows,field);Marshal.WriteInt32(rows,field,field==0?20:field==4?65536:field==8?65535:1);Check(match(ref ctx,15,table)==0&&ctx.Kind==7,"Malformed handler row accepted");Marshal.WriteInt32(rows,field,old);}
            ctx=Fresh();set(ref ctx,values[4],map,types[1]);Row(rows,0,10,20,100,types[6]);Check(match(ref ctx,15,table)==0&&ctx.Kind==7&&ctx.Pending==values[4],"Different-loader non-Throwable catch accepted");Row(rows,0,10,20,100,types[5]);
            ctx=Fresh();set(ref ctx,values[4],map,types[1]);Check(match(ref ctx,65535,table)==0&&ctx.Kind==7,"Invalid local PC accepted");
            ctx=Fresh();Check(take(ref ctx)==IntPtr.Zero&&match(ref ctx,15,table)==0,"Empty context consumed");
            // Shared immutable tables, independent per-thread Context32. All selected
            // Throwable objects remain rooted by the host until every worker completes.
            Parallel.For(0,8,worker=>{for(int n=0;n<8195;n++){
                var local=Fresh();IntPtr value=values[(n&1)==0?4:5];uint expected=(n&1)==0?201U:101U;
                Check(set(ref local,value,map,types[1])==16&&match(ref local,15,table)==expected&&take(ref local)==value,"Concurrent exception state leaked between threads");
                Check(local.Depth==3&&local.Reserved==0xfedcba9876543210UL,"Concurrent Context32 tail corrupted");
            }});
            // Explicit quiescent root: exception -> ordinary child. No stack scan or
            // automatic safepoint is implied by this test.
            Marshal.WriteIntPtr(values[4],values[0]);Marshal.WriteInt64(values[0],8,0x123456789abcdef);
            ctx=Fresh();set(ref ctx,values[4],map,types[1]);
            IntPtr contextMemory=At(data,1280);Marshal.StructureToPtr(ctx,contextMemory,false);
            for(int n=0;n<100;n++)Check(allocate(heap,16,0,new IntPtr(0x777))!=IntPtr.Zero,"Garbage allocation failed");
            Check(collect(heap,At(contextMemory,16),1)==105&&Marshal.ReadInt64(heap,56)==2,"Pending exception graph was reclaimed");
            Check(Marshal.ReadInt64(values[0],8)==0x123456789abcdef,"Live exception child changed");
            ctx=(Context32)Marshal.PtrToStructure(contextMemory,typeof(Context32));Check(match(ref ctx,20,table)==0&&ctx.Pending==values[4],"Unhandled exception root lost");
            Check(take(ref ctx)==values[4],"Post-GC Throwable identity changed");Marshal.StructureToPtr(ctx,contextMemory,false);
            Check(collect(heap,At(contextMemory,16),1)==2&&Marshal.ReadInt64(heap,56)==0,"Consumed exception graph was not reclaimable");
        } finally {if(heap!=IntPtr.Zero)Symbol<Destroy>(module,"boom_heap_destroy")(heap);if(data!=IntPtr.Zero)Marshal.FreeHGlobal(data);FreeLibrary(module);}
    }
}
