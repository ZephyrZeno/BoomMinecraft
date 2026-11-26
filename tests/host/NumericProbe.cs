using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomNumericProbe {
    // Independent test oracle for the reachable graph. Actual collection is MASM.
    public static int ReachableCount(IntPtr roots,uint count) {
        var live=new HashSet<IntPtr>();var pending=new Stack<IntPtr>();
        for(int i=0;i<count;i++)pending.Push(Marshal.ReadIntPtr(roots,i*8));
        while(pending.Count!=0) {
            IntPtr value=pending.Pop();if(value==IntPtr.Zero||!live.Add(value))continue;
            uint flags=unchecked((uint)Marshal.ReadInt32(value,-24)),refs=unchecked((uint)Marshal.ReadInt32(value,-20));long bytes=Marshal.ReadInt64(value,-16);
            if((flags&0xfffffffd)!=0xb00b0001||bytes<0||refs>(ulong)bytes/8||refs>1048576||live.Count>1048576)throw new Exception("Invalid test graph header");
            for(int i=0;i<refs;i++)pending.Push(Marshal.ReadIntPtr(value,i*8));
        }
        return live.Count;
    }
    [StructLayout(LayoutKind.Sequential)] public struct Context { public uint Kind,PC,Method,CSR; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Invoke(IntPtr entry,ref Context context,[In] ulong[] args,uint csr);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapCreate(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int HeapDestroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong HeapCollect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr StaticRoots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int BindHeap(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context context,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr ObjectLayout(uint classId);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint ReleaseTrace();
    static void ReleaseFrames(IntPtr module) {
        if(module==IntPtr.Zero)return;
        IntPtr p=GetProcAddress(module,"boom_release_trace_pool");
        if(p!=IntPtr.Zero&&Marshal.GetDelegateForFunctionPointer<ReleaseTrace>(p)()!=0)throw new Exception("Generated Java frames remained active at module shutdown");
    }
    public static void CheckExceptionOrigin(string dll,ulong[] args,uint kind,uint method,uint pc) {
        IntPtr module=LoadLibraryExW(dll,IntPtr.Zero,0x1100);if(module==IntPtr.Zero)throw new Exception("Exception probe load failed");
        try {
            var entry=Marshal.GetDelegateForFunctionPointer<Entry>(GetProcAddress(module,"boom_entry"));
            var context=new Context();ulong result=entry(ref context,args);
            if(result!=0||context.Kind!=kind||context.Method!=method||context.PC!=pc)throw new Exception("Cross-class exception origin was lost");
        }finally{FreeLibrary(module);}
    }
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapAlloc(IntPtr heap,ulong bytes,uint refs,ulong type);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr RefNew(IntPtr heap,int length,IntPtr layout,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong RefStore(IntPtr array,int index,IntPtr value,IntPtr layout,ref Context context);

    public static void CheckRetainedArray(string dll,string runtime) {
        IntPtr module=IntPtr.Zero,library=IntPtr.Zero,heap=IntPtr.Zero,roots=IntPtr.Zero,invalidLayout=IntPtr.Zero;HeapDestroy destroy=null;
        try {
            module=LoadLibraryExW(dll,IntPtr.Zero,0x1100);library=LoadLibraryExW(runtime,IntPtr.Zero,0x1100);
            if(module==IntPtr.Zero||library==IntPtr.Zero)throw new Exception("Reference array DLL load failed");
            var create=Marshal.GetDelegateForFunctionPointer<HeapCreate>(GetProcAddress(module,"boom_heap_create"));
            destroy=Marshal.GetDelegateForFunctionPointer<HeapDestroy>(GetProcAddress(module,"boom_heap_destroy"));
            var collect=Marshal.GetDelegateForFunctionPointer<HeapCollect>(GetProcAddress(module,"boom_heap_collect"));
            var bind=Marshal.GetDelegateForFunctionPointer<BindHeap>(GetProcAddress(module,"boom_bind_heap"));
            var entry=Marshal.GetDelegateForFunctionPointer<Entry>(GetProcAddress(module,"boom_entry"));
            var alloc=Marshal.GetDelegateForFunctionPointer<HeapAlloc>(GetProcAddress(library,"boom_heap_alloc"));
            var make=Marshal.GetDelegateForFunctionPointer<RefNew>(GetProcAddress(library,"boom_reference_array_new"));
            var store=Marshal.GetDelegateForFunctionPointer<RefStore>(GetProcAddress(library,"boom_reference_array_store"));
            heap=create(1024*1024);if(heap==IntPtr.Zero||bind(heap)!=1)throw new Exception("Reference heap binding failed");
            var context=new Context();IntPtr array=new IntPtr(unchecked((long)entry(ref context,new ulong[]{17})));
            if(context.Kind!=0||array==IntPtr.Zero||Marshal.ReadInt64(array,-16)!=136)throw new Exception("Translated reference array failed");
            for(int i=0;i<17;i++){IntPtr item=Marshal.ReadIntPtr(array,i*8);if(item==IntPtr.Zero||Marshal.ReadIntPtr(item,0)!=array||Marshal.ReadInt32(item,8)!=71+i)throw new Exception("Reference element/field initialization incorrect");}
            roots=Marshal.AllocHGlobal(8);Marshal.WriteIntPtr(roots,array);
            if(collect(heap,roots,1)!=0||Marshal.ReadInt64(heap,56)!=18)throw new Exception("Reference array rooted cycle was lost");
            context=new Context();entry(ref context,new ulong[]{5});
            if(context.Kind!=0||collect(heap,roots,1)!=6||Marshal.ReadInt64(heap,56)!=18)throw new Exception("Unreachable reference graph was not collected");
            IntPtr layout=Marshal.ReadIntPtr(array,-8);IntPtr previous=Marshal.ReadIntPtr(array,0);
            IntPtr wrong=alloc(heap,0,0,1);if(wrong==IntPtr.Zero)throw new Exception("Wrong-type probe allocation failed");
            context=new Context();store(array,0,wrong,layout,ref context);
            if(context.Kind!=6||Marshal.ReadIntPtr(array,0)!=previous)throw new Exception("Wrong-class array store accepted");
            context=new Context();store(array,17,wrong,layout,ref context);if(context.Kind!=5)throw new Exception("Reference bounds check precedence changed");
            context=new Context();store(IntPtr.Zero,-1,wrong,layout,ref context);if(context.Kind!=4)throw new Exception("Reference null check precedence changed");
            if(collect(heap,roots,1)!=1)throw new Exception("Rejected array element leaked a root");
            context=new Context();store(array,0,IntPtr.Zero,layout,ref context);
            if(context.Kind!=0||collect(heap,roots,1)!=1||Marshal.ReadInt64(heap,56)!=17)throw new Exception("Null array store did not release element");
            invalidLayout=Marshal.AllocHGlobal(16);Marshal.WriteInt32(invalidLayout,0,0x52454641);Marshal.WriteInt32(invalidLayout,4,2);Marshal.WriteIntPtr(invalidLayout,8,Marshal.ReadIntPtr(layout,8));
            context=new Context();if(make(heap,1,invalidLayout,ref context)!=IntPtr.Zero||context.Kind!=7)throw new Exception("Wrong reference layout ABI accepted");
            context=new Context();if(make(heap,int.MaxValue,layout,ref context)!=IntPtr.Zero||context.Kind!=3)throw new Exception("Reference array heap budget ignored");
            if(collect(heap,IntPtr.Zero,0)!=17||Marshal.ReadInt64(heap,48)!=0)throw new Exception("Final reference array root leaked");
        }finally{if(invalidLayout!=IntPtr.Zero)Marshal.FreeHGlobal(invalidLayout);if(roots!=IntPtr.Zero)Marshal.FreeHGlobal(roots);if(heap!=IntPtr.Zero&&destroy!=null)destroy(heap);if(library!=IntPtr.Zero)FreeLibrary(library);if(module!=IntPtr.Zero)FreeLibrary(module);}
    }

    // Test host only: generated Java, heap traversal and GC still run in assembly.
    public static void CheckRetainedGraph(string dll) {
        IntPtr module=IntPtr.Zero,heap=IntPtr.Zero,roots=IntPtr.Zero;HeapDestroy destroy=null;
        try {
            module=LoadLibraryExW(dll,IntPtr.Zero,0x1100);if(module==IntPtr.Zero)throw new Exception("Graph DLL load failed");
            var create=Marshal.GetDelegateForFunctionPointer<HeapCreate>(GetProcAddress(module,"boom_heap_create"));
            destroy=Marshal.GetDelegateForFunctionPointer<HeapDestroy>(GetProcAddress(module,"boom_heap_destroy"));
            var collect=Marshal.GetDelegateForFunctionPointer<HeapCollect>(GetProcAddress(module,"boom_heap_collect"));
            var bind=Marshal.GetDelegateForFunctionPointer<BindHeap>(GetProcAddress(module,"boom_bind_heap"));
            var entry=Marshal.GetDelegateForFunctionPointer<Entry>(GetProcAddress(module,"boom_entry"));
            heap=create(1024*1024);if(heap==IntPtr.Zero||bind(heap)!=1)throw new Exception("Graph heap binding failed");
            var context=new Context();IntPtr first=new IntPtr(unchecked((long)entry(ref context,new ulong[]{17})));
            if(context.Kind!=0||first==IntPtr.Zero)throw new Exception("Translated graph creation failed");
            IntPtr second=Marshal.ReadIntPtr(first,0),array=Marshal.ReadIntPtr(second,8);
            if(second==IntPtr.Zero||array==IntPtr.Zero||Marshal.ReadIntPtr(second,0)!=first)throw new Exception("Translated object cycle missing");
            if(Marshal.ReadInt64(array,-16)!=68||Marshal.ReadInt32(first,16)!=11||Marshal.ReadInt32(second,16)!=23)throw new Exception("Translated field layout incorrect");
            roots=Marshal.AllocHGlobal(8);Marshal.WriteIntPtr(roots,first);
            if(collect(heap,roots,1)!=0||Marshal.ReadInt64(heap,56)!=3)throw new Exception("Rooted graph was not retained");
            context=new Context();entry(ref context,new ulong[]{33});
            if(context.Kind!=0||collect(heap,roots,1)!=3||Marshal.ReadInt64(heap,56)!=3)throw new Exception("Unreachable graph was not reclaimed independently");
            if(Marshal.ReadIntPtr(second,0)!=first||Marshal.ReadInt64(array,-16)!=68)throw new Exception("Live graph changed during collection");
            Marshal.WriteIntPtr(first,0,IntPtr.Zero);
            if(collect(heap,roots,1)!=2||Marshal.ReadInt64(heap,56)!=1)throw new Exception("Unlinked cycle/array was not reclaimed");
            if(collect(heap,IntPtr.Zero,0)!=1||Marshal.ReadInt64(heap,48)!=0)throw new Exception("Final graph root was not reclaimed");
        }finally{if(roots!=IntPtr.Zero)Marshal.FreeHGlobal(roots);if(heap!=IntPtr.Zero&&destroy!=null)destroy(heap);if(module!=IntPtr.Zero)FreeLibrary(module);}
    }
    public static string[] Run(string dll,string fpProbe,string[] inputs,char resultType) {
        return Run(dll,fpProbe,inputs,resultType,false);
    }
    public static string[] InspectIntObject(string dll,string fpProbe,string[] inputs,int[] offsets) {
        IntPtr module=IntPtr.Zero,probe=IntPtr.Zero,heap=IntPtr.Zero,roots=IntPtr.Zero;HeapDestroy destroy=null;
        try {
            module=LoadLibraryExW(dll,IntPtr.Zero,0x1100);probe=LoadLibraryExW(fpProbe,IntPtr.Zero,0x1100);
            if(module==IntPtr.Zero||probe==IntPtr.Zero)throw new Exception("Factory probe load failed");
            var create=Marshal.GetDelegateForFunctionPointer<HeapCreate>(GetProcAddress(module,"boom_heap_create"));
            destroy=Marshal.GetDelegateForFunctionPointer<HeapDestroy>(GetProcAddress(module,"boom_heap_destroy"));
            var collect=Marshal.GetDelegateForFunctionPointer<HeapCollect>(GetProcAddress(module,"boom_heap_collect"));
            var bind=Marshal.GetDelegateForFunctionPointer<BindHeap>(GetProcAddress(module,"boom_bind_heap"));
            var invoke=Marshal.GetDelegateForFunctionPointer<Invoke>(GetProcAddress(probe,"boom_probe_numeric"));
            IntPtr entry=GetProcAddress(module,"boom_entry");heap=create(1024*1024);
            if(heap==IntPtr.Zero||bind(heap)!=1)throw new Exception("Factory heap bind failed");
            roots=Marshal.AllocHGlobal(8);var results=new string[inputs.Length];
            for(int i=0;i<inputs.Length;i++) {
                var parts=inputs[i].Split(new[]{' '},StringSplitOptions.RemoveEmptyEntries);var args=new ulong[parts.Length];
                for(int j=0;j<args.Length;j++)args[j]=Convert.ToUInt64(parts[j],16);
                foreach(uint csr in new uint[]{0x1f80,0xffc0}) {
                    var context=new Context();IntPtr value=new IntPtr(unchecked((long)invoke(entry,ref context,args,csr)));
                    if(value==IntPtr.Zero||context.Kind!=0||context.CSR!=csr)throw new Exception("Actual factory assembly failed");
                    Marshal.WriteIntPtr(roots,value);
                    if(collect(heap,roots,1)!=0||Marshal.ReadInt64(heap,56)!=1)throw new Exception("Actual factory object was not retained");
                    var fields=new string[offsets.Length];for(int j=0;j<offsets.Length;j++)fields[j]=Marshal.ReadInt32(value,offsets[j]).ToString(System.Globalization.CultureInfo.InvariantCulture);
                    string actual=String.Join(" ",fields);if(results[i]!=null&&results[i]!=actual)throw new Exception("Factory depends on caller FP state");results[i]=actual;
                    if(collect(heap,IntPtr.Zero,0)!=1||Marshal.ReadInt64(heap,48)!=0)throw new Exception("Actual factory object was not reclaimed");
                }
            }
            return results;
        }finally{if(roots!=IntPtr.Zero)Marshal.FreeHGlobal(roots);if(heap!=IntPtr.Zero&&destroy!=null)destroy(heap);if(probe!=IntPtr.Zero)FreeLibrary(probe);if(module!=IntPtr.Zero)FreeLibrary(module);}
    }
    public static string[] Run(string dll,string fpProbe,string[] inputs,char resultType,bool useHeap) {
        return Run(dll,fpProbe,inputs,resultType,useHeap,null,null);
    }
    public static string[] Run(string dll,string fpProbe,string[] inputs,char resultType,bool useHeap,uint[] exceptionClasses,string[] exceptionNames) {
        IntPtr module=IntPtr.Zero,probe=IntPtr.Zero,heap=IntPtr.Zero;HeapDestroy destroy=null;HeapCollect collect=null;
        try {
            module=LoadLibraryExW(dll,IntPtr.Zero,0x1100);probe=LoadLibraryExW(fpProbe,IntPtr.Zero,0x1100);
            if(module==IntPtr.Zero||probe==IntPtr.Zero)throw new Exception("LoadLibrary failed: "+Marshal.GetLastWin32Error());
            IntPtr entry=GetProcAddress(module,"boom_entry"),symbol=GetProcAddress(probe,"boom_probe_numeric");
            if(entry==IntPtr.Zero||symbol==IntPtr.Zero)throw new Exception("Missing assembly export");
            var invoke=Marshal.GetDelegateForFunctionPointer<Invoke>(symbol);var results=new string[inputs.Length];
            var exceptionTypes=new Dictionary<IntPtr,string>();
            if(exceptionClasses!=null){
                if(exceptionNames==null||exceptionClasses.Length!=exceptionNames.Length)throw new Exception("Invalid exception metadata");
                var layout=Marshal.GetDelegateForFunctionPointer<ObjectLayout>(GetProcAddress(module,"boom_get_object_layout"));
                for(int i=0;i<exceptionClasses.Length;i++){IntPtr tag=layout(exceptionClasses[i]);if(tag==IntPtr.Zero)throw new Exception("Missing exception layout");exceptionTypes.Add(tag,exceptionNames[i]);}
            }
            if(useHeap) {
                var create=Marshal.GetDelegateForFunctionPointer<HeapCreate>(GetProcAddress(module,"boom_heap_create"));
                destroy=Marshal.GetDelegateForFunctionPointer<HeapDestroy>(GetProcAddress(module,"boom_heap_destroy"));
                collect=Marshal.GetDelegateForFunctionPointer<HeapCollect>(GetProcAddress(module,"boom_heap_collect"));
                var bind=Marshal.GetDelegateForFunctionPointer<BindHeap>(GetProcAddress(module,"boom_bind_heap"));
                heap=create(16*1024*1024);if(heap==IntPtr.Zero)throw new Exception("Test heap creation failed");if(bind(heap)!=1)throw new Exception("Assembly heap ABI mismatch");
            }
            for(int i=0;i<inputs.Length;i++) {
                var parts=inputs[i].Split(new[]{' '},StringSplitOptions.RemoveEmptyEntries);var values=new ulong[parts.Length];
                for(int a=0;a<parts.Length;a++)values[a]=Convert.ToUInt64(parts[a],16);
                foreach(uint csr in new uint[]{0x1f80,0xffc0}) {
                    var context=new Context();ulong bits=invoke(entry,ref context,values,csr);
                    if(context.CSR!=csr)throw new Exception("Generated code failed to restore caller MXCSR");
                    string actual;
                    if(context.Kind!=0) {
                        if(context.Kind==16){
                            IntPtr pending=new IntPtr(unchecked((long)bits));string name;
                            if(heap==IntPtr.Zero||pending.ToInt64()<heap.ToInt64()+160||pending.ToInt64()>Marshal.ReadInt64(heap,24)||!exceptionTypes.TryGetValue(Marshal.ReadIntPtr(pending,-8),out name))throw new Exception("Unknown pending exception object");
                            actual="e "+name;
                        }else{
                        string[] errors={"","java.lang.ArithmeticException","java.lang.NegativeArraySizeException","java.lang.OutOfMemoryError","java.lang.NullPointerException","java.lang.ArrayIndexOutOfBoundsException","java.lang.ArrayStoreException","java.lang.VerifyError","java.lang.ExceptionInInitializerError","java.lang.NoClassDefFoundError","java.lang.StackOverflowError","java.lang.StringIndexOutOfBoundsException","java.lang.ClassCastException","java.lang.IncompatibleClassChangeError","java.lang.AbstractMethodError","java.lang.IllegalAccessError",null,"java.lang.IllegalMonitorStateException","java.lang.IllegalArgumentException","java.lang.ClassNotFoundException","java.lang.UnsatisfiedLinkError","java.io.IOException","java.io.SyncFailedException","java.lang.InternalError"};
                        if(context.Kind>=errors.Length||errors[context.Kind]==null)throw new Exception("Unknown exception kind");actual="e "+errors[context.Kind];
                        }
                    }
                    else {
                        if(resultType=='I'||resultType=='F')bits&=0xffffffff;
                        if(resultType=='F'&&(bits&0x7f800000)==0x7f800000&&(bits&0x7fffff)!=0)bits=0x7fc00000;
                        if(resultType=='D'&&(bits&0x7ff0000000000000UL)==0x7ff0000000000000UL&&(bits&0xfffffffffffffUL)!=0)bits=0x7ff8000000000000UL;
                        actual="v "+bits.ToString("x16");
                    }
                    if(results[i]!=null&&results[i]!=actual)throw new Exception("Numeric result depends on caller FP state");
                    results[i]=actual;
                    if(useHeap) {
                        IntPtr symbolRoots=GetProcAddress(module,"boom_get_static_roots"),staticRoots=IntPtr.Zero;uint rootCount=0;
                        if(symbolRoots!=IntPtr.Zero)staticRoots=Marshal.GetDelegateForFunctionPointer<StaticRoots>(symbolRoots)(out rootCount);
                        if(rootCount>65536)throw new Exception("Static root ABI mismatch");
                        int live=ReachableCount(staticRoots,rootCount);
                        if(collect(heap,staticRoots,rootCount)==ulong.MaxValue||Marshal.ReadInt64(heap,56)!=live||(live==0&&Marshal.ReadInt64(heap,48)!=0))throw new Exception("Post-entry quiescent/static-root GC failed");
                    }
                }
            }
            return results;
        }finally{ReleaseFrames(module);if(heap!=IntPtr.Zero&&destroy!=null)destroy(heap);if(probe!=IntPtr.Zero)FreeLibrary(probe);if(module!=IntPtr.Zero)FreeLibrary(module);}
    }
}
