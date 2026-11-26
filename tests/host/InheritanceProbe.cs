using System;
using System.Runtime.InteropServices;
public static class BoomInheritanceProbe {
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr HeapCreate(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int HeapDestroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolRun(IntPtr pool,IntPtr entry,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint PoolDestroy(IntPtr pool);
    static T Symbol<T>(IntPtr module,string name)where T:Delegate {var p=GetProcAddress(module,name);if(p==IntPtr.Zero)throw new Exception("Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static IntPtr Open(string path){var m=LoadLibraryExW(path,IntPtr.Zero,0x1100);if(m==IntPtr.Zero)throw new Exception("Cannot open "+path);return m;}
    public static void Cold(string dll,string runtime,int expectedPayload) {
        IntPtr module=Open(dll),library=IntPtr.Zero,heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try{
            library=Open(runtime);heap=Symbol<HeapCreate>(module,"boom_heap_create")(4*1024*1024);
            if(heap==IntPtr.Zero||Symbol<Bind>(module,"boom_bind_heap")(heap)!=1)throw new Exception("Inherited graph heap failed");
            const int count=4099;var values=new long[count*16];for(int i=0;i<count;i++)values[i*16]=i;
            input=Marshal.AllocHGlobal(count*128);output=Marshal.AllocHGlobal(count*32);Marshal.Copy(values,0,input,values.Length);
            pool=Symbol<PoolCreate>(library,"boom_pool_create")(8);if(pool==IntPtr.Zero)throw new Exception("Inherited graph pool failed");
            if(Symbol<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)!=0)throw new Exception("Inherited graph cold run failed");
            var actual=new long[count*4];Marshal.Copy(output,actual,0,actual.Length);
            for(int i=0;i<count;i++)if(actual[i*4]!=91+i||actual[i*4+1]!=0||actual[i*4+2]!=0||actual[i*4+3]!=0)throw new Exception("Inherited constructor/field publication mismatch "+i);
            uint rootCount;var roots=Symbol<Roots>(module,"boom_get_static_roots")(out rootCount);IntPtr root=IntPtr.Zero,rootSlot=IntPtr.Zero;
            for(int i=0;i<rootCount;i++){var p=Marshal.ReadIntPtr(roots,i*8);if(p==IntPtr.Zero)continue;if(root!=IntPtr.Zero)throw new Exception("Unexpected inherited graph root");root=p;rootSlot=IntPtr.Add(roots,i*8);}
            if(root==IntPtr.Zero||Marshal.ReadInt32(root,-20)!=3||Marshal.ReadInt64(root,-16)!=expectedPayload||Marshal.ReadInt64(heap,56)!=4)throw new Exception("Inherited physical object shape mismatch");
            int[] expected={17,12,14};for(int i=0;i<3;i++){var token=Marshal.ReadIntPtr(root,i*8);if(token==IntPtr.Zero||Marshal.ReadInt32(token)!=expected[i])throw new Exception("Private/hidden reference identity mismatch");}
            var collect=Symbol<Collect>(module,"boom_heap_collect");if(collect(heap,roots,rootCount)!=0||Marshal.ReadInt64(heap,56)!=4)throw new Exception("Inherited reference graph was not retained");
            Marshal.WriteIntPtr(root,0,IntPtr.Zero);if(collect(heap,roots,rootCount)!=1||Marshal.ReadInt64(heap,56)!=3)throw new Exception("Cleared private parent field was not reclaimed");
            Marshal.WriteIntPtr(rootSlot,IntPtr.Zero);if(collect(heap,roots,rootCount)!=3||Marshal.ReadInt64(heap,56)!=0)throw new Exception("Inherited graph leaked after clearing root");
        }finally{if(pool!=IntPtr.Zero)Symbol<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Symbol<HeapDestroy>(module,"boom_heap_destroy")(heap);if(library!=IntPtr.Zero)FreeLibrary(library);FreeLibrary(module);}
    }
}
