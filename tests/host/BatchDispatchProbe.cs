using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

// Development host only: original getter bodies, type lookup and dispatch run
// assembly. Receivers have source layouts; Java constructors are not executed.
public static class BoomBatchDispatchProbe {
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string path,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Make(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ArrayNew(IntPtr heap,long length,uint kind,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(IntPtr ctx,IntPtr argv);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Kernel(IntPtr ctx,IntPtr argv,IntPtr table,IntPtr constraints);
    static void Need(bool value,string message){if(!value)throw new Exception(message);}
    static IntPtr Open(string path){IntPtr p=LoadLibraryExW(path,IntPtr.Zero,0x1100);Need(p!=IntPtr.Zero,"Cannot load "+path);return p;}
    static IntPtr Address(IntPtr module,string name){IntPtr p=GetProcAddress(module,name);Need(p!=IntPtr.Zero,"Missing "+name);return p;}
    static T Function<T>(IntPtr module,string name) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(Address(module,name));}
    static void Reset(IntPtr ctx){for(int i=0;i<32;i+=8)Marshal.WriteInt64(ctx,i,0);Marshal.WriteInt32(ctx,4,0x3456);Marshal.WriteInt32(ctx,8,0x789);}
    static void Error(IntPtr ctx,uint kind){Need(unchecked((uint)Marshal.ReadInt32(ctx))==kind,"Unexpected dispatch error");Need(Marshal.ReadInt32(ctx,4)==0x3456&&Marshal.ReadInt32(ctx,8)==0x789&&Marshal.ReadInt32(ctx,12)==0,"Dispatch overwrote caller location/depth");}
    public static long[] Run(string runtime,string dll,string directory,string directName,uint bufferId,uint objectId,string equalsName){
        IntPtr library=Open(runtime),module=IntPtr.Zero,heap=IntPtr.Zero,ctx=IntPtr.Zero,argv=IntPtr.Zero,table=IntPtr.Zero,rows=IntPtr.Zero,constraints=IntPtr.Zero;
        try{
            module=Open(dll);ctx=Marshal.AllocHGlobal(32);argv=Marshal.AllocHGlobal(16);Reset(ctx);
            var create=Function<Create>(library,"boom_heap_create");var destroy=Function<Destroy>(library,"boom_heap_destroy");
            var make=Function<Make>(library,"boom_object_new");var array=Function<ArrayNew>(library,"boom_array_new");
            heap=create(4*1024*1024);Need(heap!=IntPtr.Zero,"Cannot create dispatch heap");
            IntPtr map=Address(module,"boom_runtime_type_map"),types=Address(module,"boom_batch_type_descriptors");
            IntPtr sourceRows=Marshal.ReadIntPtr(map,16);int rowCount=Marshal.ReadInt32(map,8);
            var layouts=new Dictionary<int,IntPtr>();
            for(int i=0;i<rowCount;i++){IntPtr row=IntPtr.Add(sourceRows,i*40);if(Marshal.ReadInt32(row,20)==0)layouts.Add(Marshal.ReadInt32(row,16),Marshal.ReadIntPtr(row));}
            var names=new Dictionary<string,int>();
            foreach(string line in File.ReadLines(Path.Combine(directory,"types.tsv"))){string[] p=line.Split('\t');if(!names.ContainsKey(p[0]))names.Add(p[0],int.Parse(p[1]));}
            var objects=new List<IntPtr>();var expectedDirect=new List<int>();var classIds=new List<int>();
            foreach(string line in File.ReadLines(Path.Combine(directory,"oracle.tsv"))){
                string[] p=line.Split('\t');int id;if(!names.TryGetValue(p[0],out id))continue;IntPtr value=make(heap,layouts[id],ctx);
                Need(value!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Source Buffer receiver allocation failed: "+p[0]);
                objects.Add(value);classIds.Add(id);expectedDirect.Add(int.Parse(p[1]));
            }
            Need(objects.Count>=4,"Too few distinct original ByteBuffer classes");
            var direct=Function<Entry>(module,directName);
            // Cold parallel first use exercises the real ABI2 type-index CAS.
            long warmBytes=Marshal.ReadInt64(heap,48);const int workers=8,rounds=2048;
            Parallel.For(0,workers,worker=>{
                IntPtr context=Marshal.AllocHGlobal(32),arguments=Marshal.AllocHGlobal(16);
                try{
                    for(int n=0;n<rounds;n++){
                        int index=(n+worker)%objects.Count;Reset(context);Marshal.WriteIntPtr(arguments,objects[index]);
                        Need(direct(context,arguments)==(ulong)expectedDirect[index]&&Marshal.ReadInt32(context)==0,"Original isDirect dispatch differs from JVM");
                        Need(Marshal.ReadInt32(context,12)==0,"Original getter leaked call depth");
                    }
                    // Visit every source class regardless of the round count.
                    for(int index=0;index<objects.Count;index++){
                        Reset(context);Marshal.WriteIntPtr(arguments,objects[index]);
                        Need(direct(context,arguments)==(ulong)expectedDirect[index]&&Marshal.ReadInt32(context)==0,"Source ByteBuffer class missing from dispatch");
                    }
                }finally{Marshal.FreeHGlobal(context);Marshal.FreeHGlobal(arguments);}
            });
            Need(Marshal.ReadInt64(heap,48)==warmBytes,"Dispatch/getters allocated guest memory");
            int errors=0;Reset(ctx);Marshal.WriteIntPtr(argv,IntPtr.Zero);Need(direct(ctx,argv)==0,"Null receiver returned a value");Error(ctx,4);errors++;
            Reset(ctx);IntPtr plain=make(heap,layouts[(int)objectId],ctx);Marshal.WriteIntPtr(argv,plain);
            Need(direct(ctx,argv)==0,"Unrelated receiver invoked a target");Error(ctx,13);errors++;
            for(int kind=1;kind<=23;kind++){
                Reset(ctx);Marshal.WriteInt32(ctx,kind);Marshal.WriteInt64(ctx,16,0x1122334455667788L);Marshal.WriteIntPtr(argv,objects[0]);
                Need(direct(ctx,argv)==0,"Pending error invoked target");Error(ctx,(uint)kind);
                Need(Marshal.ReadInt64(ctx,16)==0x1122334455667788L,"Pending Throwable root changed");errors++;
            }
            var kernel=Function<Kernel>(module,"boom_batch_virtual_invoke");
            table=Marshal.AllocHGlobal(40);rows=Marshal.AllocHGlobal(16);constraints=Marshal.AllocHGlobal(16);
            for(int i=0;i<40;i+=8)Marshal.WriteInt64(table,i,0);
            Marshal.WriteInt32(table,unchecked((int)0x56445350));Marshal.WriteInt32(table,4,1);
            Marshal.WriteInt32(table,8,1);Marshal.WriteIntPtr(table,16,rows);Marshal.WriteInt32(table,32,13);
            Marshal.WriteInt32(rows,classIds[0]);Marshal.WriteIntPtr(rows,8,IntPtr.Zero);
            IntPtr objectType=Marshal.ReadIntPtr(types,(int)objectId*8),bufferType=Marshal.ReadIntPtr(types,(int)bufferId*8);
            Marshal.WriteIntPtr(constraints,bufferType);Marshal.WriteIntPtr(constraints,8,bufferType);Marshal.WriteIntPtr(argv,objects[0]);
            foreach(int kind in new int[]{13,14,15}){Reset(ctx);Marshal.WriteInt32(rows,4,kind);Need(kernel(ctx,argv,table,constraints)==0,"Selection error invoked target");Error(ctx,(uint)kind);errors++;}
            // Independently require both symbolic-owner and protected constraints.
            foreach(int which in new int[]{0,8}){
                Marshal.WriteIntPtr(constraints,objectType);Marshal.WriteIntPtr(constraints,8,objectType);Marshal.WriteIntPtr(constraints,which,bufferType);
                Reset(ctx);Marshal.WriteIntPtr(argv,plain);Need(kernel(ctx,argv,table,constraints)==0,"A receiver constraint was skipped");Error(ctx,13);errors++;
            }
            Marshal.WriteIntPtr(constraints,objectType);Marshal.WriteIntPtr(constraints,8,objectType);
            Marshal.WriteInt32(table,8,0);Marshal.WriteIntPtr(table,24,Address(module,equalsName));Marshal.WriteInt32(table,32,0);
            Reset(ctx);IntPtr ints=array(heap,2,10,ctx);Need(ints!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Primitive-array allocation failed");
            Marshal.WriteIntPtr(argv,ints);Marshal.WriteIntPtr(argv,8,ints);Need(kernel(ctx,argv,table,constraints)==1&&Marshal.ReadInt32(ctx)==0,"Array Object.equals identity failed");
            Marshal.WriteIntPtr(argv,8,plain);Need(kernel(ctx,argv,table,constraints)==0&&Marshal.ReadInt32(ctx)==0,"Array Object.equals inequality failed");
            Reset(ctx);Marshal.WriteInt32(table,0);Need(kernel(ctx,argv,table,constraints)==0,"Bad table was accepted");Error(ctx,7);errors++;
            return new long[]{objects.Count,workers*(rounds+objects.Count),workers,errors,2};
        }finally{
            if(heap!=IntPtr.Zero)Function<Destroy>(library,"boom_heap_destroy")(heap);
            foreach(IntPtr p in new IntPtr[]{ctx,argv,table,rows,constraints})if(p!=IntPtr.Zero)Marshal.FreeHGlobal(p);
            if(module!=IntPtr.Zero)FreeLibrary(module);FreeLibrary(library);
        }
    }
}
