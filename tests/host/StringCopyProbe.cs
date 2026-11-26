// Original Java prepend executes in AOT ASM. F/R cases invoke the ASM storage
// ABI directly with explicitly constructed VM String/byte[] fixtures.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
public static class BoomStringCopyProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context { public uint Kind,PC,Method,Depth; public ulong Pending,Plan; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Indexed(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Load(IntPtr h,IntPtr pool,uint i,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(ref Context c,[In]ulong[] args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Service(ref Context c,[In]ulong[] args,IntPtr pool,uint op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Release();
    static void Check(bool condition,string message) { if(!condition) throw new Exception(message); }
    static T Fn<T>(IntPtr image,string name) { IntPtr p=GetProcAddress(image,name);Check(p!=IntPtr.Zero,"Missing "+name);return Marshal.GetDelegateForFunctionPointer<T>(p); }
    static ulong Bits(IntPtr p) { return unchecked((ulong)p.ToInt64()); }
    static IntPtr Text(Alloc alloc,IntPtr heap,IntPtr layout,string encoded) {
        if(encoded=="null") return IntPtr.Zero;
        string[] units=encoded.Length==0?Array.Empty<string>():encoded.Split(':');
        IntPtr chars=alloc(heap,(ulong)units.Length*2,0,261),text=alloc(heap,16,1,Bits(layout));
        Check(chars!=IntPtr.Zero&&text!=IntPtr.Zero,"String storage fixture allocation failed");
        for(int i=0;i<units.Length;i++) Marshal.WriteInt16(chars,i*2,unchecked((short)Convert.ToUInt16(units[i],16)));
        Marshal.WriteIntPtr(text,chars);return text;
    }
    static IntPtr Buffer(Alloc alloc,IntPtr heap,int capacity) {
        if(capacity<0) return IntPtr.Zero;
        IntPtr buffer=alloc(heap,(ulong)capacity,0,264);Check(buffer!=IntPtr.Zero,"Byte array fixture allocation failed");
        for(int i=0;i<capacity;i++) Marshal.WriteByte(buffer,i,0x5a);return buffer;
    }
    static string Bytes(IntPtr buffer,int capacity) {
        if(buffer==IntPtr.Zero) return "null";
        byte[] bytes=new byte[capacity];Marshal.Copy(buffer,bytes,0,capacity);return BitConverter.ToString(bytes).Replace("-","").ToLowerInvariant();
    }
    public static string[] Run(string dll,string runtime,string[] cases,uint[] ids,string[] names) {
        IntPtr image=LoadLibraryExW(dll,IntPtr.Zero,0x1100),rt=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;
        Check(image!=IntPtr.Zero&&rt!=IntPtr.Zero,"String copy image load failed");
        try {
            heap=Fn<Create>(rt,"boom_heap_create")(16777216);Check(heap!=IntPtr.Zero&&Fn<One>(image,"boom_bind_heap")(heap)==1,"String copy heap bind failed");
            IntPtr pool=Fn<Pointer>(image,"boom_get_storage_string_pool")(),layout=Marshal.ReadIntPtr(pool,40);
            Check(Marshal.ReadInt32(pool,16)>0,"Original prepend image lacks a literal for pool binding");
            var init=new Context();Check(Fn<Load>(rt,"boom_string_load")(heap,pool,0,ref init)!=IntPtr.Zero&&init.Kind==0,"String pool binding failed");
            var alloc=Fn<Alloc>(rt,"boom_heap_alloc");var entry=Fn<Entry>(image,"boom_entry32");var service=Fn<Service>(rt,"boom_string_intrinsic");
            var typeNames=new Dictionary<IntPtr,string>();var getLayout=Fn<Indexed>(image,"boom_get_object_layout");
            for(int i=0;i<ids.Length;i++) typeNames[getLayout(ids[i])]=names[i];
            var results=new List<string>();
            foreach(string line in cases) {
                string[] p=line.Split('|');int src=int.Parse(p[1]),dst=int.Parse(p[2]),count=int.Parse(p[3]),capacity=int.Parse(p[4]);
                IntPtr text=Text(alloc,heap,layout,p[5]),buffer=Buffer(alloc,heap,capacity);var c=new Context();ulong value;
                if(p[0]=="P") { int length=p[5]=="null"||p[5].Length==0?0:p[5].Split(':').Length;value=entry(ref c,new[]{0x100000000UL+unchecked((uint)(dst+length)),Bits(buffer),Bits(text)}); }
                else if(p[0]=="F") value=service(ref c,new[]{Bits(text),Bits(buffer),unchecked((ulong)(long)dst),1UL},pool,24);
                else value=service(ref c,new[]{Bits(text),Bits(buffer),unchecked((ulong)(long)src),unchecked((ulong)(long)dst),1UL,unchecked((ulong)(long)count)},pool,25);
                Check(c.Depth==0,"String copy leaked a Java frame");string result;
                if(c.Kind==0) result="v "+value.ToString("x16");
                else { string name;if(c.Kind==16) { Check(c.Pending!=0,"Missing Java exception");name=typeNames[Marshal.ReadIntPtr(new IntPtr(unchecked((long)c.Pending)),-8)]; }
                    else if(c.Kind==4) name="java.lang.NullPointerException";
                    else if(c.Kind==5) name="java.lang.ArrayIndexOutOfBoundsException";
                    else throw new Exception("Unexpected string copy kind="+c.Kind+" at "+line);
                    result="e "+name;
                }
                results.Add(result+" "+Bytes(buffer,capacity));
            }
            // Per-worker arrays keep writes independent; warmed Java prepend
            // and both ASM ABIs must copy without allocating guest objects.
            IntPtr[] texts=new IntPtr[8],buffers=new IntPtr[8];
            for(int i=0;i<8;i++) { texts[i]=Text(alloc,heap,layout,"0:41:ff:100:d800:dc00:ffff:62");buffers[i]=Buffer(alloc,heap,32); }
            var warm=new Context();entry(ref warm,new[]{0x10000000aUL,Bits(buffers[0]),Bits(texts[0])});Check(warm.Kind==0,"Original prepend warmup failed");
            long before=Marshal.ReadInt64(heap,48);
            Parallel.For(0,8,worker=>{for(int i=0;i<256;i++) { var c=new Context();ulong value=entry(ref c,new[]{0x10000000aUL,Bits(buffers[worker]),Bits(texts[worker])});Check(c.Kind==0&&c.Depth==0&&value==0x100000002UL,"Parallel original prepend failed");
                var f=new Context();service(ref f,new[]{Bits(texts[worker]),Bits(buffers[worker]),2UL,1UL},pool,24);Check(f.Kind==0,"Parallel full byte copy failed");
                var g=new Context();service(ref g,new[]{Bits(texts[worker]),Bits(buffers[worker]),1UL,4UL,1UL,3UL},pool,25);Check(g.Kind==0,"Parallel range byte copy failed");
                Check(Marshal.ReadInt16(buffers[worker],8)==0x41&&Marshal.ReadInt16(buffers[worker],10)==0xff&&Marshal.ReadInt16(buffers[worker],12)==0x100,"Parallel UTF16 bytes differ");
            }});
            Check(Marshal.ReadInt64(heap,48)==before,"Warm string byte copies allocated guest objects");return results.ToArray();
        } finally { if(image!=IntPtr.Zero)Check(Fn<Release>(image,"boom_release_trace_pool")()==0,"String copy frames remain");if(heap!=IntPtr.Zero)Fn<One>(rt,"boom_heap_destroy")(heap);if(rt!=IntPtr.Zero)FreeLibrary(rt);if(image!=IntPtr.Zero)FreeLibrary(image); }
    }
}
