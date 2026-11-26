using System;
using System.Runtime.InteropServices;
// Development verification host only. Java bodies, receiver dispatch, class
// initialization, allocation and worker execution all remain assembly.
public static class BoomInterfaceDispatchProbe {
    [StructLayout(LayoutKind.Sequential)] public struct Context {public uint Kind,PC,Method,Depth;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapCreate(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int HeapDestroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Layout(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr NewObject(IntPtr heap,IntPtr layout,ref Context context);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context context,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr pool,IntPtr entry,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr pool);
    static T Symbol<T>(IntPtr m,string name) where T:Delegate {var p=GetProcAddress(m,name);if(p==IntPtr.Zero)throw new Exception("Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static IntPtr Open(string path){var m=LoadLibraryExW(path,IntPtr.Zero,0x1100);if(m==IntPtr.Zero)throw new Exception("Cannot open "+path);return m;}
    public static void Cold(string dll,string runtime) {
        IntPtr module=Open(dll),library=IntPtr.Zero,heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try {
            library=Open(runtime);heap=Symbol<HeapCreate>(module,"boom_heap_create")(4*1024*1024);
            if(heap==IntPtr.Zero||Symbol<Bind>(module,"boom_bind_heap")(heap)!=1)throw new Exception("Cold dispatch heap failed");
            const int count=4099;var values=new long[count*16];for(int i=0;i<count;i++)values[i*16]=i;
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(values,0,input,values.Length);
            pool=Symbol<PoolCreate>(library,"boom_pool_create")(8);if(pool==IntPtr.Zero)throw new Exception("Dispatch pool failed");
            if(Symbol<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)!=0)throw new Exception("Cold dispatch failed");
            var actual=new long[count*4];Marshal.Copy(output,actual,0,actual.Length);
            for(int i=0;i<count;i++)if(actual[i*4]!=12402+i||actual[i*4+1]!=0||actual[i*4+2]!=0||actual[i*4+3]!=0)throw new Exception("Cold default initialization/dispatch mismatch "+i);
        }finally{if(pool!=IntPtr.Zero)Symbol<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);if(library!=IntPtr.Zero)FreeLibrary(library);FreeLibrary(module);}
    }
    public static void Receivers(string dll,string runtime,uint pending,uint plain,uint right,uint entryId) {
        IntPtr module=Open(dll),library=IntPtr.Zero,heap=IntPtr.Zero;
        try {
            library=Open(runtime);heap=Symbol<HeapCreate>(module,"boom_heap_create")(1024*1024);
            if(heap==IntPtr.Zero||Symbol<Bind>(module,"boom_bind_heap")(heap)!=1)throw new Exception("Dispatch receiver heap failed");
            var layout=Symbol<Layout>(module,"boom_get_object_layout");var make=Symbol<NewObject>(library,"boom_object_new");var entry=Symbol<Entry>(module,"boom_entry");
            foreach(uint id in new[]{pending,plain,right}) {
                var context=new Context();var shape=layout(id);if(shape==IntPtr.Zero)throw new Exception("Missing dispatch layout");
                var value=make(heap,shape,ref context);if(value==IntPtr.Zero||context.Kind!=0)throw new Exception("Dispatch receiver setup failed");
                context=new Context();ulong result=entry(ref context,new[]{unchecked((ulong)value.ToInt64()),7UL});
                uint expected=id==pending?14U:id==plain?13U:0U;
                if(context.Kind!=expected||context.Depth!=0||(expected!=0&&(result!=0||context.Method!=entryId))||(expected==0&&result!=9))throw new Exception("Wrong dispatch receiver status "+id+" "+context.Kind);
            }
            var nullContext=new Context();entry(ref nullContext,new[]{0UL,7UL});if(nullContext.Kind!=4||nullContext.Depth!=0)throw new Exception("Null dispatch receiver status changed");
        }finally{if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);if(library!=IntPtr.Zero)FreeLibrary(library);FreeLibrary(module);}
    }
}
