using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
public static class BoomClockProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {public uint Kind,PC,Method,Depth;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string file,IntPtr reserved,uint flags);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr module,string name);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr module);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Filetime(ulong value);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Counter(ulong count,ulong frequency);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong bytes);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Roots(out uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Collect(IntPtr heap,IntPtr roots,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context ctx,[In] ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr PoolCreate(uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int PoolRun(IntPtr pool,IntPtr entry,IntPtr input,IntPtr output,uint count);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int PoolDestroy(IntPtr pool);
    static void Check(bool pass,string message){if(!pass)throw new Exception(message);}
    static IntPtr Open(string path){IntPtr p=LoadLibraryExW(path,IntPtr.Zero,0x1100);Check(p!=IntPtr.Zero,"Clock module load failed");return p;}
    static T Fn<T>(IntPtr module,string name){IntPtr p=GetProcAddress(module,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    public static void Arithmetic(string runtime,string[] filetimes,string[] counters){
        IntPtr module=Open(runtime);
        try{
            var filetime=Fn<Filetime>(module,"boom_vm_filetime_to_millis");var counter=Fn<Counter>(module,"boom_vm_counter_to_nanos");
            foreach(string line in filetimes){var p=line.Split(' ');Check(filetime(Convert.ToUInt64(p[0],16))==Convert.ToUInt64(p[1],16),"FILETIME conversion mismatch: "+line);}
            foreach(string line in counters){var p=line.Split(' ');Check(counter(Convert.ToUInt64(p[0],16),Convert.ToUInt64(p[1],16))==Convert.ToUInt64(p[2],16),"Counter conversion mismatch: "+line);}
        }finally{FreeLibrary(module);}
    }
    public static void Samples(string dll,int kind){
        IntPtr module=Open(dll),heap=IntPtr.Zero;
        try{
            heap=Fn<Create>(module,"boom_heap_create")(1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Clock heap setup failed");
            var entry=Fn<Entry>(module,"boom_entry");long previous=long.MinValue;bool changed=false;
            for(int i=0;i<1000;i++){
                long wallBefore=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),ticksBefore=Stopwatch.GetTimestamp();
                var ctx=new Context();ulong raw=entry(ref ctx,new ulong[]{kind==2?128UL:kind==3?1000UL:0UL});
                long ticksAfter=Stopwatch.GetTimestamp(),wallAfter=DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),value=unchecked((long)raw);
                Check(ctx.Kind==0&&ctx.PC==0&&ctx.Method==0&&ctx.Depth==0,"Clock service damaged its Java context");
                if(kind==0)Check(value>=Math.Min(wallBefore,wallAfter)-32&&value<=Math.Max(wallBefore,wallAfter)+32,"Clock epoch/units differ from Windows UTC time");
                else if(kind==1){
                    double low=ticksBefore*(1000000000.0/Stopwatch.Frequency),high=ticksAfter*(1000000000.0/Stopwatch.Frequency);
                    Check(value>=low-4096&&value<=high+4096,"Native nanoTime is outside its QPC call interval");
                    Check(value>=previous,"nanoTime moved backwards");if(previous!=long.MinValue&&value!=previous)changed=true;previous=value;
                }else if(kind==2)Check(value==1,"Generated nanoTime loop was not monotonic");
                else if(kind==3)Check(value>=0&&value<=1000000000L,"Elapsed nanoTime interval is invalid");
                else throw new Exception("Unknown clock test kind");
            }
            if(kind==1)Check(changed,"nanoTime was constant over the sample run");
            uint rootCount;IntPtr roots=Fn<Roots>(module,"boom_get_static_roots")(out rootCount);
            Check(Marshal.ReadInt64(heap,56)==0&&Fn<Collect>(module,"boom_heap_collect")(heap,roots,rootCount)==0,"Clock calls allocated guest heap objects");
        }finally{if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);FreeLibrary(module);}
    }
    public static void Parallel(string dll,string runtime){
        IntPtr module=Open(dll),library=IntPtr.Zero,heap=IntPtr.Zero,pool=IntPtr.Zero,input=IntPtr.Zero,output=IntPtr.Zero;
        try{
            library=Open(runtime);heap=Fn<Create>(module,"boom_heap_create")(1024*1024);Check(heap!=IntPtr.Zero&&Fn<Bind>(module,"boom_bind_heap")(heap)==1,"Parallel clock heap failed");
            const int count=8195;var values=new long[count*16];for(int i=0;i<count;i++)values[i*16]=16;
            input=Marshal.AllocHGlobal(values.Length*8);Marshal.Copy(values,0,input,values.Length);output=Marshal.AllocHGlobal(count*32);
            pool=Fn<PoolCreate>(library,"boom_pool_create")(8);Check(pool!=IntPtr.Zero,"Parallel clock pool failed");
            Check(Fn<PoolRun>(library,"boom_pool_run")(pool,GetProcAddress(module,"boom_entry"),input,output,count)==0,"Parallel clock dispatch failed");
            var results=new long[count*4];Marshal.Copy(output,results,0,results.Length);
            for(int i=0;i<count;i++)Check(results[i*4]==1&&results[i*4+1]==0&&results[i*4+2]==0&&results[i*4+3]==0,"Parallel nanoTime/context mismatch");
            Check(Marshal.ReadInt64(heap,56)==0,"Parallel clock allocated guest objects");
        }finally{if(pool!=IntPtr.Zero)Fn<PoolDestroy>(library,"boom_pool_destroy")(pool);if(input!=IntPtr.Zero)Marshal.FreeHGlobal(input);if(output!=IntPtr.Zero)Marshal.FreeHGlobal(output);if(heap!=IntPtr.Zero)Fn<Destroy>(module,"boom_heap_destroy")(heap);if(library!=IntPtr.Zero)FreeLibrary(library);FreeLibrary(module);}
    }
}
