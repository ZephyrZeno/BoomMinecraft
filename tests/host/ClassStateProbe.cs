// Development host only: translated methods, class synchronization and GC are assembly.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomClassStateProbe {
    [StructLayout(LayoutKind.Sequential)] public struct Context {public uint Kind,PC,Method,Reserved;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context context,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapCreate(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int HeapDestroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Descriptor(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Field(uint id,uint field);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr pool,IntPtr entry,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr pool);
    static T Symbol<T>(IntPtr module,string name) where T:Delegate {
        IntPtr pointer=GetProcAddress(module,name);if(pointer==IntPtr.Zero)throw new Exception("Missing "+name);
        return Marshal.GetDelegateForFunctionPointer<T>(pointer);
    }
    static IntPtr Open(string path) {IntPtr module=LoadLibraryExW(path,IntPtr.Zero,0x1100);if(module==IntPtr.Zero)throw new Exception("Module load failed: "+path);return module;}
    static void Gc(IntPtr module,IntPtr heap) {
        uint count;IntPtr roots=Symbol<Roots>(module,"boom_get_static_roots")(out count);
        if(count>65536)throw new Exception("Static root count invalid");
        var live=new HashSet<IntPtr>();for(int i=0;i<count;i++){IntPtr value=Marshal.ReadIntPtr(roots,i*8);if(value!=IntPtr.Zero)live.Add(value);}
        if(Symbol<Collect>(module,"boom_heap_collect")(heap,roots,count)==ulong.MaxValue||Marshal.ReadInt64(heap,56)!=live.Count)throw new Exception("Static reference GC failed");
    }
    static IntPtr MakeHeap(IntPtr module) {
        IntPtr heap=Symbol<HeapCreate>(module,"boom_heap_create")(16*1024*1024);
        if(heap==IntPtr.Zero)throw new Exception("State heap failed");
        if(Symbol<Bind>(module,"boom_bind_heap")(heap)!=1){Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);throw new Exception("State heap binding failed");}
        IntPtr second=Symbol<HeapCreate>(module,"boom_heap_create")(16*1024*1024);
        if(second==IntPtr.Zero){Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);throw new Exception("Second binding probe allocation failed");}
        int rebound=Symbol<Bind>(module,"boom_bind_heap")(second);
        Symbol<HeapDestroy>(module,"boom_heap_destroy")(second);
        if(rebound!=0){Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);throw new Exception("Module with static roots accepted a different heap");}
        return heap;
    }
    public static string[] Sequence(string dll,string[] inputs,bool heapRequired) {
        IntPtr module=Open(dll),heap=IntPtr.Zero;
        try {
            if(heapRequired)heap=MakeHeap(module);
            var entry=Symbol<Entry>(module,"boom_entry");var results=new string[inputs.Length];
            string[] errors={"","java.lang.ArithmeticException","java.lang.NegativeArraySizeException","java.lang.OutOfMemoryError","java.lang.NullPointerException","java.lang.ArrayIndexOutOfBoundsException","java.lang.ArrayStoreException","java.lang.VerifyError","java.lang.ExceptionInInitializerError","java.lang.NoClassDefFoundError","java.lang.StackOverflowError"};
            for(int i=0;i<inputs.Length;i++){
                var text=inputs[i].Split(new[]{' '},StringSplitOptions.RemoveEmptyEntries);var args=new ulong[text.Length];for(int j=0;j<args.Length;j++)args[j]=Convert.ToUInt64(text[j],16);
                var context=new Context();ulong value=entry(ref context,args);
                if(context.Kind>=errors.Length)throw new Exception("Unknown initializer exception");
                results[i]=context.Kind==0?"v "+(value&0xffffffff).ToString("x16"):"e "+errors[context.Kind];
                if(heap!=IntPtr.Zero)Gc(module,heap);
            }
            return results;
        }finally{if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);FreeLibrary(module);}
    }
    public static void CheckFailure(string dll,bool heapRequired,uint owner,uint initializer,uint firstKind,uint causeKind,uint causePc,int retainedArrays) {
        IntPtr module=Open(dll),heap=IntPtr.Zero;
        try {
            if(heapRequired)heap=MakeHeap(module);
            var entry=Symbol<Entry>(module,"boom_entry");var context=new Context();entry(ref context,new ulong[0]);
            if(context.Kind!=firstKind)throw new Exception("First initializer failure kind incorrect");
            IntPtr descriptor=Symbol<Descriptor>(module,"boom_get_class_descriptor")(owner);
            if(descriptor==IntPtr.Zero||Marshal.ReadInt32(descriptor,8)!=3||Marshal.ReadInt32(descriptor,12)!=0||unchecked((uint)Marshal.ReadInt32(descriptor,32))!=causeKind||unchecked((uint)Marshal.ReadInt32(descriptor,36))!=causePc||unchecked((uint)Marshal.ReadInt32(descriptor,40))!=initializer)throw new Exception("Original initializer failure was not retained");
            context=new Context();entry(ref context,new ulong[0]);if(context.Kind!=9)throw new Exception("Erroneous class was initialized again");
            if(heap!=IntPtr.Zero){Gc(module,heap);if(Marshal.ReadInt64(heap,56)!=retainedArrays)throw new Exception("Partially initialized static roots were lost");}
        }finally{if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);FreeLibrary(module);}
    }
    public static void CheckField(string dll,uint owner,uint field,ulong expected) {
        IntPtr module=Open(dll);
        try {IntPtr address=Symbol<Field>(module,"boom_get_static_field")(owner,field);if(address==IntPtr.Zero||unchecked((ulong)Marshal.ReadInt64(address))!=expected)throw new Exception("ConstantValue preparation mismatch");}
        finally{FreeLibrary(module);}
    }
    public static void StackLimit(string dll,uint[] classes) {
        IntPtr module=Open(dll);
        try {
            var entry=Symbol<Entry>(module,"boom_entry");var descriptor=Symbol<Descriptor>(module,"boom_get_class_descriptor");
            var context=new Context();ulong result=entry(ref context,new ulong[0]);
            if(result!=0||context.Kind!=10||context.Reserved!=0)throw new Exception("Bounded guest stack did not unwind safely");
            for(int i=0;i<classes.Length;i++)if(Marshal.ReadInt32(descriptor(classes[i]),8)!=(i<128?3:0))throw new Exception("Stack failure initialization boundary incorrect: "+i);
            context=new Context();entry(ref context,new ulong[0]);if(context.Kind!=9||context.Reserved!=0)throw new Exception("Stack failure class state/depth was not persistent");
        }finally{FreeLibrary(module);}
    }
    public static void ColdParallel(string dll,string runtime,uint raceClass,uint runsField,uint expected) {
        IntPtr module=Open(dll),library=Open(runtime),pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try {
            const int count=4099;var values=new long[count*16];for(int i=0;i<count;i++)values[i*16]=i;
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(values,0,input,values.Length);
            pool=Symbol<PoolCreate>(library,"boom_pool_create")(8);if(pool==IntPtr.Zero)throw new Exception("Cold pool creation failed");
            if(Symbol<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)!=0)throw new Exception("Cold pool failed");
            var actual=new long[count*4];Marshal.Copy(output,actual,0,actual.Length);
            for(int i=0;i<count;i++)if(unchecked((ulong)actual[i*4])!=(expected^(uint)i)||actual[i*4+1]!=0||actual[i*4+2]!=0||actual[i*4+3]!=0)throw new Exception("Unpublished class state observed by worker "+i);
            IntPtr runs=Symbol<Field>(module,"boom_get_static_field")(raceClass,runsField),descriptor=Symbol<Descriptor>(module,"boom_get_class_descriptor")(raceClass);
            if(Marshal.ReadInt32(runs)!=1||Marshal.ReadInt32(descriptor,8)!=2||Marshal.ReadInt32(descriptor,12)!=0)throw new Exception("Initializer execution/publication count invalid");
        }finally{if(pool!=IntPtr.Zero)Symbol<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);FreeLibrary(module);FreeLibrary(library);}
    }
    public static void FailureParallel(string dll,string runtime,bool heapRequired,uint owner,uint rootMethod,uint initializer,int retained) {
        IntPtr module=Open(dll),library=Open(runtime),heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try {
            if(heapRequired)heap=MakeHeap(module);
            const int count=4099;input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);
            Marshal.Copy(new long[count*16],0,input,count*16);pool=Symbol<PoolCreate>(library,"boom_pool_create")(8);
            if(pool==IntPtr.Zero)throw new Exception("Failure pool creation failed");
            for(int batch=0;batch<2;batch++) {
                if(Symbol<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)!=0)throw new Exception("Failure pool failed");
                var actual=new long[count*4];Marshal.Copy(output,actual,0,actual.Length);int first=0,later=0;
                for(int i=0;i<count;i++) {
                    ulong status=unchecked((ulong)actual[i*4+1]);uint kind=(uint)status,pc=(uint)(status>>32);
                    if(kind==8)first++;else if(kind==9)later++;else throw new Exception("Invalid concurrent initializer exception");
                    if(actual[i*4]!=0||pc!=0||unchecked((ulong)actual[i*4+2])!=rootMethod||actual[i*4+3]!=0)throw new Exception("Concurrent class failure context changed");
                }
                if(first!=(batch==0?1:0)||later!=count-first)throw new Exception("Failed class initialization was replayed");
                if(heap!=IntPtr.Zero){Gc(module,heap);if(Marshal.ReadInt64(heap,56)!=retained)throw new Exception("Concurrent failed class lost static roots");}
            }
            IntPtr descriptor=Symbol<Descriptor>(module,"boom_get_class_descriptor")(owner);
            if(Marshal.ReadInt32(descriptor,8)!=3||Marshal.ReadInt32(descriptor,12)!=0||Marshal.ReadInt32(descriptor,32)!=1||unchecked((uint)Marshal.ReadInt32(descriptor,40))!=initializer)throw new Exception("Concurrent original failure was not retained");
        }finally{if(pool!=IntPtr.Zero)Symbol<PoolDestroy>(library,"boom_pool_destroy")(pool);if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);FreeLibrary(module);FreeLibrary(library);}
    }
}
