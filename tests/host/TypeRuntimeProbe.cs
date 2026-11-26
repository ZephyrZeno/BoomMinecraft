using System;
using System.Runtime.InteropServices;

public static class BoomTypeRuntimeProbe {
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Descriptor(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Count();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Assign(IntPtr from,IntPtr to);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(uint jobs);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint RunPool(IntPtr pool,IntPtr entry,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Destroy(IntPtr pool);
    static T Symbol<T>(IntPtr module,string name) where T:Delegate {var value=GetProcAddress(module,name);if(value==IntPtr.Zero)throw new Exception("Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(value);}
    static IntPtr Open(string path){var value=LoadLibraryExW(path,IntPtr.Zero,0x1100);if(value==IntPtr.Zero)throw new Exception("Cannot load "+path);return value;}
    public static void Run(string dll,string runtime,int count,int[] expected) {
        IntPtr module=Open(dll),library=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try {
            library=Open(runtime);
            if(Symbol<Count>(module,"boom_get_type_count")()!=count||expected.Length!=count*count)throw new Exception("Type count mismatch");
            var descriptor=Symbol<Descriptor>(module,"boom_get_type_descriptor");var assign=Symbol<Assign>(module,"boom_type_assignable");
            if(descriptor((uint)count)!=IntPtr.Zero||descriptor(uint.MaxValue)!=IntPtr.Zero)throw new Exception("Type getter bounds failed");
            if(assign(IntPtr.Zero,IntPtr.Zero)!=0)throw new Exception("Null metadata accepted");
            IntPtr bad=Marshal.AllocHGlobal(40);
            try {
                Marshal.Copy(new int[10],0,bad,10);
                if(assign(bad,bad)!=0)throw new Exception("Invalid metadata accepted");
                Marshal.WriteInt32(bad,0,0x54595045);Marshal.WriteInt32(bad,4,2);
                if(assign(bad,bad)!=0)throw new Exception("Invalid metadata ABI accepted");
                Marshal.WriteInt32(bad,4,1);Marshal.WriteInt32(bad,8,4);
                if(assign(bad,bad)!=0)throw new Exception("Invalid metadata kind accepted");
            }finally{Marshal.FreeHGlobal(bad);}
            for(int from=0;from<count;from++)for(int to=0;to<count;to++)if(assign(descriptor((uint)from),descriptor((uint)to))!=expected[from*count+to])throw new Exception("Sequential type mismatch "+from+" -> "+to);
            var values=new long[expected.Length*16];
            for(int from=0;from<count;from++)for(int to=0;to<count;to++){int offset=(from*count+to)*16;values[offset]=from;values[offset+1]=to;}
            input=Marshal.AllocHGlobal(expected.Length*128);output=Marshal.AllocHGlobal(expected.Length*32);Marshal.Copy(values,0,input,values.Length);
            foreach(uint jobs in new uint[]{1,2,4,8}) {
                pool=Symbol<Create>(library,"boom_pool_create")(jobs);if(pool==IntPtr.Zero)throw new Exception("Type pool creation failed");
                for(int batch=0;batch<3;batch++) {
                    if(Symbol<RunPool>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_type_probe_entry"),input,output,(uint)expected.Length)!=0)throw new Exception("Type pool failed");
                    var actual=new long[expected.Length*4];Marshal.Copy(output,actual,0,actual.Length);
                    for(int i=0;i<expected.Length;i++)if(actual[i*4]!=expected[i]||actual[i*4+1]!=0||actual[i*4+2]!=0||actual[i*4+3]!=0)throw new Exception("Parallel type mismatch "+i+" at "+jobs+" workers");
                }
                if(Symbol<Destroy>(library,"boom_pool_destroy")(pool)!=0)throw new Exception("Type pool destruction failed");pool=IntPtr.Zero;
            }
        }finally{if(pool!=IntPtr.Zero)Symbol<Destroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(library!=IntPtr.Zero)FreeLibrary(library);FreeLibrary(module);}
    }
}
