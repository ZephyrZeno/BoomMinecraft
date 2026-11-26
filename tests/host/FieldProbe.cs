// Development host. All Field operations and original callers execute in ASM.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
public static class BoomFieldProbe {
    [StructLayout(LayoutKind.Sequential)]struct Context{public uint Kind,PC,Method,Depth;public ulong Pending,Plan;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)]static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")]static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Entry(ref Context c,[In]ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Service(ref Context c,[In]ulong[] a,IntPtr pool,uint op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Address(ref Context c,IntPtr baseObject,ulong offset,IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int Contains(IntPtr h,IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate uint Release();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Alloc(IntPtr h,ulong bytes,uint refs,ulong tag);
    static void Check(bool b,string s){if(!b)throw new Exception(s);}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static ulong Bits(IntPtr p){return unchecked((ulong)p.ToInt64());}
    static IntPtr Ptr(ulong p){return new IntPtr(unchecked((long)p));}
    static IntPtr Zero(int bytes){IntPtr p=Marshal.AllocHGlobal(bytes);Marshal.Copy(new byte[bytes],0,p,bytes);return p;}
    static uint StringHash(IntPtr text){IntPtr chars=Marshal.ReadIntPtr(text);int length=checked((int)(Marshal.ReadInt64(chars,-16)/2));uint hash=0;for(int i=0;i<length;i++)hash=unchecked(hash*31+(ushort)Marshal.ReadInt16(chars,i*2));return hash;}
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Indexed(uint id);
    // Registration ABI test with explicit VM Set12/site fixtures. No Set factory
    // or Java registerFieldsToFilter caller is executed by this test.
    public static string[] CheckFilterAbi(string dll,string runtime,uint targetClass,bool clearCache){
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;Check(m!=IntPtr.Zero&&r!=IntPtr.Zero,"Filter ABI images");var owned=new List<IntPtr>();
        try{
            heap=Fn<Create>(r,"boom_heap_create")(16777216);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Filter ABI heap");var entry=Fn<Entry>(m,"boom_entry32");var c=new Context();IntPtr first=Ptr(entry(ref c,new[]{0UL}));Check(c.Kind==0&&first!=IntPtr.Zero,"Filter first token");var secondContext=new Context();IntPtr second=Ptr(entry(ref secondContext,new[]{1UL}));Check(secondContext.Kind==0,"Filter second token");
            var observations=new List<string>();IntPtr targetState=Fn<Indexed>(m,"boom_get_class_descriptor")(targetClass);Check(Marshal.ReadInt32(targetState,8)==0,"Filter target initialized before registration");
            IntPtr original=Fn<Pointer>(m,"boom_get_field_pool")();Check(Marshal.ReadInt32(original,4)==4,"Filter ABI requires FLDS4");
            IntPtr pool=Zero(144),site=Zero(64),names=Zero(32),rows=Zero(8),layout=Zero(24);owned.AddRange(new[]{pool,site,names,rows,layout});byte[] bytes=new byte[144];Marshal.Copy(original,bytes,0,144);Marshal.Copy(bytes,0,pool,144);
            Marshal.WriteIntPtr(pool,112,site);Marshal.WriteInt32(pool,120,1);Marshal.WriteInt32(site,0,0x1010);Marshal.WriteInt32(site,4,0x2020);Marshal.WriteInt32(site,8,Marshal.ReadInt32(Marshal.ReadIntPtr(first,8)));Marshal.WriteInt32(site,12,2);Marshal.WriteIntPtr(site,16,layout);Marshal.WriteInt32(site,24,0);Marshal.WriteInt32(site,28,8);Marshal.WriteIntPtr(site,32,names);Marshal.WriteIntPtr(site,40,rows);Marshal.WriteInt32(site,48,2);
            Marshal.WriteInt32(layout,0,0x4f424a43);Marshal.WriteInt32(layout,4,2);Marshal.WriteInt64(layout,8,16);Marshal.WriteInt32(layout,16,2);Marshal.WriteInt32(layout,20,2);
            var service=Fn<Service>(r,"boom_field_service");IntPtr baseObject=Marshal.ReadIntPtr(first);IntPtr set=Fn<Alloc>(r,"boom_heap_alloc")(heap,16,2,Bits(layout));Check(set!=IntPtr.Zero,"Set12 storage fixture allocation");
            var nameHashes=new uint[2];for(int i=0;i<2;i++){IntPtr token=i==0?first:second;var nameContext=c;IntPtr name=Ptr(service(ref nameContext,new[]{Bits(token)},original,1));Check(nameContext.Kind==0&&name!=IntPtr.Zero,"Filter actual name fixture");nameHashes[i]=StringHash(name);Marshal.WriteIntPtr(set,i*8,name);IntPtr chars=Marshal.ReadIntPtr(name);Marshal.WriteIntPtr(names,i*16,chars);Marshal.WriteInt32(names,i*16+8,checked((int)(Marshal.ReadInt64(chars,-16)/2)));long index=(Marshal.ReadIntPtr(token,8).ToInt64()-Marshal.ReadIntPtr(original,48).ToInt64())/64;Marshal.WriteInt32(rows,i*4,checked((int)index));}
            observations.Add(nameHashes[0].ToString("x"));observations.Add(nameHashes[0].ToString("x"));observations.Add(nameHashes[1].ToString("x"));var textContext=new Context();IntPtr textToken=Ptr(entry(ref textContext,new[]{2UL}));var textNameContext=c;IntPtr textName=Ptr(service(ref textNameContext,new[]{Bits(textToken)},original,1));Check(textContext.Kind==0&&textNameContext.Kind==0,"Filter unrelated field baseline");uint textHash=StringHash(textName);observations.Add(textHash.ToString("x"));
            if(clearCache){int targetType=Marshal.ReadInt32(site,8);Marshal.WriteInt32(Marshal.ReadIntPtr(original,136),targetType*4,0);}
            int winners=0,duplicates=0;Parallel.For(0,8,worker=>{for(int i=0;i<128;i++){var local=c;local.PC=0x2020;local.Method=0x1010;service(ref local,new[]{Bits(baseObject),Bits(set)},pool,11);if(local.Kind==0)System.Threading.Interlocked.Increment(ref winners);else if(local.Kind==18)System.Threading.Interlocked.Increment(ref duplicates);else throw new Exception("Filter ABI race kind="+local.Kind);}});Check(winners==1&&duplicates==1023,"Filter ABI publication not atomic");
            Check(Marshal.ReadInt32(targetState,8)==0,"Registration initialized target class");observations.Add("0");
            var old=c;IntPtr oldName=Ptr(service(ref old,new[]{Bits(first)},original,1));Check(oldName!=IntPtr.Zero&&old.Kind==0,"Previously obtained Field was revoked");observations.Add(StringHash(oldName).ToString("x"));
            foreach(ulong which in new[]{0UL,1UL}){var lookup=new Context();ulong value=entry(ref lookup,new[]{which});if(clearCache){Check(value==0&&lookup.Kind==16&&lookup.Pending!=0,"Fresh reflection cache did not apply runtime filter");IntPtr message=Marshal.ReadIntPtr(Ptr(lookup.Pending),Marshal.ReadInt32(original,88));observations.Add((0x71000000u^StringHash(message)).ToString("x"));}else{Check(value!=0&&lookup.Kind==0,"Late registration changed existing reflection cache");observations.Add(nameHashes[which].ToString("x"));}}
            var kept=new Context();Check(entry(ref kept,new[]{2UL})!=0&&kept.Kind==0,"Filter hid an unrelated field");observations.Add(textHash.ToString("x"));observations.Add("72000000");observations.Add(Marshal.ReadInt32(targetState,8)==0?"0":"1");return observations.ToArray();
        }finally{Finish(m,r,heap);foreach(IntPtr p in owned)Marshal.FreeHGlobal(p);}
    }
    static void Finish(IntPtr m,IntPtr r,IntPtr heap){if(m!=IntPtr.Zero&&GetProcAddress(m,"boom_release_trace_pool")!=IntPtr.Zero)Check(Fn<Release>(m,"boom_release_trace_pool")()==0,"Field frames remain active");if(heap!=IntPtr.Zero)Fn<One>(r,"boom_heap_destroy")(heap);if(r!=IntPtr.Zero)FreeLibrary(r);if(m!=IntPtr.Zero)FreeLibrary(m);}
    public static string[] Run(string dll,string runtime,string[] cases){
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero;Check(m!=IntPtr.Zero&&r!=IntPtr.Zero,"Field query images");
        try{
            heap=Fn<Create>(r,"boom_heap_create")(33554432);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Field query heap");var entry=Fn<Entry>(m,"boom_entry32");var results=new List<string>();
            foreach(string line in cases){string[] p=line.Split(' ');var c=new Context();ulong value=entry(ref c,new[]{(ulong)(uint)int.Parse(p[0]),(ulong)(uint)int.Parse(p[1])});Check(c.Kind==0&&c.Depth==0,"Field query failed at "+line+" kind="+c.Kind+" method="+c.Method+" pc="+c.PC);results.Add(value.ToString("x"));}
            Parallel.For(0,8,worker=>{for(int i=0;i<128;i++){var c=new Context();ulong value=entry(ref c,new[]{4UL,(ulong)(i%5)});Check(c.Kind==0&&c.Depth==0&&value==6,"Concurrent fresh Field/equality differs");}});
            return results.ToArray();
        }finally{Finish(m,r,heap);}
    }
    public static void CheckAbi(string dll,string runtime){
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100),heap=IntPtr.Zero,combined=IntPtr.Zero;Check(m!=IntPtr.Zero&&r!=IntPtr.Zero,"Field ABI images");
        try{
            heap=Fn<Create>(r,"boom_heap_create")(1048576);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Field ABI heap");var entry=Fn<Entry>(m,"boom_entry32");
            var c=new Context();IntPtr token=Ptr(entry(ref c,new[]{0UL}));Check(c.Kind==0&&token!=IntPtr.Zero,"Original caller did not allocate Field token");
            IntPtr pool=Fn<Pointer>(m,"boom_get_field_pool")(),row=Marshal.ReadIntPtr(token,8),baseObject=Marshal.ReadIntPtr(token);var service=Fn<Service>(r,"boom_field_service");
            long live=Marshal.ReadInt64(heap,56);var ready=c;ulong bits=service(ref ready,new[]{Bits(token)},pool,3);Check(ready.Kind==0&&(bits&0x4a)==0x4a,"Full runtime Field modifiers");
            ready=c;Check(service(ref ready,new[]{Bits(token)},pool,4)==Bits(baseObject)&&ready.Kind==0,"Full runtime declaring class identity");
            ready=c;ulong offset=service(ref ready,new[]{0UL,Bits(token)},pool,5);Check(ready.Kind==0&&(offset>>32)==0x424f4f4d,"Opaque static offset token");
            ready=c;Check(service(ref ready,new[]{0UL,Bits(token)},pool,6)==Bits(baseObject)&&ready.Kind==0,"Static base identity");
            ready=c;Check(Fn<Address>(r,"boom_field_static_address")(ref ready,baseObject,offset,pool)==Marshal.ReadIntPtr(row,32)&&ready.Kind==0,"Canonical static cell mapping");
            Check(Marshal.ReadInt64(heap,56)==live,"Static offset/base metadata access allocated Java memory");
            foreach(int slot in new[]{16,24}){long old=Marshal.ReadInt64(token,slot);Marshal.WriteInt64(token,slot,slot==16?0:1);try{ready=c;service(ref ready,new[]{Bits(token)},pool,3);Check(ready.Kind==7,"Malformed Field token accepted");}finally{Marshal.WriteInt64(token,slot,old);}}
            ready=c;Fn<Address>(r,"boom_field_static_address")(ref ready,baseObject,0x424f4f4dffffffffUL,pool);Check(ready.Kind==18,"Out-of-range static token accepted");
            var pending=new Context{Kind=16,PC=3,Method=5,Depth=2,Pending=7,Plan=11};service(ref pending,null,IntPtr.Zero,0);Check(pending.Kind==16&&pending.PC==3&&pending.Method==5&&pending.Depth==2&&pending.Pending==7&&pending.Plan==11,"Pending Field context changed");
            Check(Marshal.ReadInt64(Fn<Pointer>(m,"boom_get_trace_pool")(),32)==0,"Field ABI frames remain active");
            IntPtr source=Fn<Roots>(m,"boom_get_static_roots")(out uint count);combined=Marshal.AllocHGlobal(checked((int)(count+1)*8));for(int i=0;i<count;i++)Marshal.WriteIntPtr(combined,i*8,Marshal.ReadIntPtr(source,i*8));Marshal.WriteIntPtr(combined,(int)count*8,token);
            Check(Fn<Collect>(r,"boom_heap_collect")(heap,combined,count+1)!=ulong.MaxValue&&Fn<Contains>(r,"boom_heap_contains")(heap,token)==1,"Live Field graph was not rooted");
            ready=c;Check(service(ref ready,new[]{Bits(token)},pool,4)==Bits(baseObject)&&ready.Kind==0,"Field declaring class lost after GC");
            Marshal.WriteIntPtr(combined,(int)count*8,IntPtr.Zero);Fn<Collect>(r,"boom_heap_collect")(heap,combined,count+1);Check(Fn<Contains>(r,"boom_heap_contains")(heap,token)==0,"Temporary Field token was not reclaimed");
        }finally{if(combined!=IntPtr.Zero)Marshal.FreeHGlobal(combined);Finish(m,r,heap);}
    }
}
