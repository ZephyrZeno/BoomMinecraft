// Isolated VM metadata/String fixtures, actual full assembly runtime and Winsock.
// This does not execute the original InetAddress Java initializer or Minecraft.
using System;
using System.Runtime.InteropServices;
using System.Threading.Tasks;

public static class BoomInetAvailabilityProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context {
        public uint Kind, PC, Method, Depth;
        public ulong Pending, Plan;
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p, IntPtr z, uint f);
    [DllImport("kernel32.dll", CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m, string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Init(ref Context c, IntPtr a, IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Query(ref Context c, IntPtr a, IntPtr p, uint op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr h, ulong n, uint refs, ulong tag);
    static void Check(bool b, string s) { if (!b) throw new Exception(s); }
    static T Fn<T>(IntPtr m, string n) {
        IntPtr p=GetProcAddress(m,n); Check(p!=IntPtr.Zero,"Missing "+n);
        return Marshal.GetDelegateForFunctionPointer<T>(p);
    }
    static IntPtr Zero(int n) { IntPtr p=Marshal.AllocHGlobal(n); Marshal.Copy(new byte[n],0,p,n); return p; }
    static ulong Bits(IntPtr p) { return unchecked((ulong)p.ToInt64()); }
    static IntPtr Text(Alloc alloc, IntPtr h, IntPtr layout, string text) {
        if (text==null) return IntPtr.Zero;
        IntPtr chars=alloc(h,(ulong)text.Length*2,0,261);
        Check(chars!=IntPtr.Zero,"char[] fixture allocation");
        for (int i=0;i<text.Length;i++) Marshal.WriteInt16(chars,i*2,unchecked((short)text[i]));
        IntPtr value=alloc(h,16,1,Bits(layout)); Check(value!=IntPtr.Zero,"String fixture allocation");
        Marshal.WriteIntPtr(value,chars); return value;
    }
    public static void Run(string fixture, string runtime, string[] preferences, string[] expected) {
        IntPtr m=LoadLibraryExW(fixture,IntPtr.Zero,0x1100), r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100);
        Check(m!=IntPtr.Zero && r!=IntPtr.Zero,"Network probe image load");
        IntPtr heap=IntPtr.Zero, other=IntPtr.Zero, pool=Zero(64), strings=Zero(80), layout=Zero(24), cell=Zero(8);
        try {
            var create=Fn<Create>(r,"boom_heap_create"); var alloc=Fn<Alloc>(r,"boom_heap_alloc");
            heap=create(1048576); other=create(4096); Check(heap!=IntPtr.Zero && other!=IntPtr.Zero,"Network fixture heaps");
            Marshal.WriteInt32(layout,0,0x4f424a43); Marshal.WriteInt32(layout,4,1);
            Marshal.WriteInt64(layout,8,16); Marshal.WriteInt32(layout,16,1); Marshal.WriteInt32(layout,20,2);
            Marshal.WriteInt32(strings,0,0x53545250); Marshal.WriteInt32(strings,4,3);
            Marshal.WriteIntPtr(strings,40,layout); Marshal.WriteIntPtr(strings,48,heap);
            IntPtr cache=Fn<Pointer>(m,"boom_get_inet_cache")(), owner=Marshal.ReadIntPtr(cache,16);
            Marshal.WriteInt32(owner,8,2); var init=Fn<Init>(r,"boom_inet_address_init");
            var c=new Context(); init(ref c,IntPtr.Zero,cache); Check(c.Kind==0,"Network metadata initialization");
            Marshal.WriteInt32(pool,0,0x56415049); Marshal.WriteInt32(pool,4,1);
            Marshal.WriteIntPtr(pool,16,cell); Marshal.WriteIntPtr(pool,24,strings); Marshal.WriteIntPtr(pool,32,cache);
            var query=Fn<Query>(r,"boom_inet_address_available");
            for (int index=0;index<preferences.Length;index++) {
                string preference=preferences[index]; string[] pair=expected[index].Split(' ');
                uint[] values={uint.Parse(pair[0]),uint.Parse(pair[1])};
                Marshal.WriteIntPtr(cell,Text(alloc,heap,layout,preference));
                for (int offset=8;offset<16;offset+=4) Marshal.WriteInt32(pool,offset,0);
                for (int offset=40;offset<64;offset+=4) Marshal.WriteInt32(pool,offset,0);
                long span=Marshal.ReadInt64(heap,48), count=Marshal.ReadInt64(heap,56);
                Parallel.For(0,8,worker=> {
                    for (uint i=0;i<128;i++) {
                        uint op=(i+(uint)worker)&1; var local=new Context();
                        uint value=query(ref local,IntPtr.Zero,pool,op);
                        Check(local.Kind==0 && value==values[op],"JVM availability differs at "+index+" op "+op);
                    }
                });
                Check(Marshal.ReadInt32(pool,8)==2 && Marshal.ReadInt32(pool,48)==1,"Availability was probed more than once");
                Check(Marshal.ReadInt64(heap,48)==span && Marshal.ReadInt64(heap,56)==count,"Availability allocated Java objects");
                bool prefer=string.Equals(preference,"true",StringComparison.OrdinalIgnoreCase);
                Check(Marshal.ReadInt32(pool,52)==(prefer?1:0),"IPv4 preference snapshot differs");
                Marshal.WriteIntPtr(cell,Text(alloc,heap,layout,prefer?"false":"true"));
                for (uint op=0;op<2;op++) { c=new Context(); Check(query(ref c,IntPtr.Zero,pool,op)==values[op] && c.Kind==0,"Availability cache reread property"); }
            }
            c=new Context{Kind=16,PC=11,Method=13,Depth=2,Pending=17,Plan=19};
            Check(query(ref c,IntPtr.Zero,IntPtr.Zero,0)==0 && c.Kind==16 && c.PC==11 && c.Method==13 && c.Depth==2 && c.Pending==17 && c.Plan==19,"Pending exception changed");
            c=new Context(); query(ref c,IntPtr.Zero,pool,2); Check(c.Kind==7,"Bad query accepted");
            Marshal.WriteInt32(pool,8,0); Marshal.WriteInt32(cache,8,0);
            c=new Context(); query(ref c,IntPtr.Zero,pool,0); Check(c.Kind==7 && Marshal.ReadInt32(pool,8)==0,"Uninitialized cache accepted");
            Marshal.WriteInt32(cache,8,2);
            foreach (int offset in new[]{0,4,8,60}) {
                int old=Marshal.ReadInt32(pool,offset); Marshal.WriteInt32(pool,offset,-1);
                c=new Context(); query(ref c,IntPtr.Zero,pool,0); Check(c.Kind==7,"Malformed availability metadata "+offset);
                Marshal.WriteInt32(pool,offset,old);
            }
            Marshal.WriteIntPtr(cell,Text(alloc,other,layout,"true"));
            c=new Context(); query(ref c,IntPtr.Zero,pool,0); Check(c.Kind==7 && Marshal.ReadInt32(pool,8)==0,"Foreign heap property accepted");
            IntPtr nonString=alloc(heap,0,0,261); Check(nonString!=IntPtr.Zero,"Non-String fixture allocation");
            Marshal.WriteIntPtr(cell,nonString);
            c=new Context(); query(ref c,IntPtr.Zero,pool,0); Check(c.Kind==7 && Marshal.ReadInt32(pool,8)==0,"Non-String property accepted");
            Marshal.WriteIntPtr(cell,IntPtr.Zero); c=new Context(); query(ref c,IntPtr.Zero,pool,0);
            Check(c.Kind==0 && Marshal.ReadInt32(pool,8)==2,"Availability failed to recover");
            Marshal.WriteInt32(pool,8,3); Marshal.WriteInt32(pool,12,20);
            c=new Context{PC=5,Method=7}; query(ref c,IntPtr.Zero,pool,0);
            Check(c.Kind==20 && c.PC==5 && c.Method==7,"Cached startup error lost its source");
        } finally {
            if(other!=IntPtr.Zero) Fn<Destroy>(r,"boom_heap_destroy")(other);
            if(heap!=IntPtr.Zero) Fn<Destroy>(r,"boom_heap_destroy")(heap);
            foreach(IntPtr p in new[]{pool,strings,layout,cell}) Marshal.FreeHGlobal(p);
            if(r!=IntPtr.Zero) FreeLibrary(r); if(m!=IntPtr.Zero) FreeLibrary(m);
        }
    }
}
