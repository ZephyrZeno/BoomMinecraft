// Disposable CLI controller for the assembly name catalog and generated Java initializers.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
public static class BoomClassNameProbe {
    [StructLayout(LayoutKind.Sequential)] struct Context{public uint Kind,PC,Method,Depth;public ulong Pending,Plan;}
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)]static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)]static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")]static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int One(IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Indexed(uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Field(uint owner,uint field);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Load(IntPtr heap,IntPtr pool,uint id,ref Context c);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Entry(ref Context c,[In]ulong[] a);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Service(ref Context c,[In]ulong[] a,IntPtr p);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Alloc(IntPtr h,ulong n,uint refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate IntPtr Roots(out uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate ulong Collect(IntPtr h,IntPtr roots,uint n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate uint Release();
    static void Check(bool v,string why){if(!v)throw new Exception(why);}
    static T Fn<T>(IntPtr m,string n){IntPtr p=GetProcAddress(m,n);Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p);}
    static ulong Bits(IntPtr p){return unchecked((ulong)p.ToInt64());}
    static void GC(IntPtr m,IntPtr heap,params IntPtr[] extra){IntPtr roots=Fn<Roots>(m,"boom_get_static_roots")(out uint n),all=Marshal.AllocHGlobal(checked(((int)n+extra.Length)*8));try{for(int i=0;i<n;i++)Marshal.WriteIntPtr(all,i*8,Marshal.ReadIntPtr(roots,i*8));for(int i=0;i<extra.Length;i++)Marshal.WriteIntPtr(all,((int)n+i)*8,extra[i]);Check(Fn<Collect>(m,"boom_heap_collect")(heap,all,n+(uint)extra.Length)!=ulong.MaxValue,"Reflection root collection failed");}finally{Marshal.FreeHGlobal(all);}}

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int Bind(IntPtr p,uint key,IntPtr value);
    static string Hex(string s){if(s==null)return "null";if(s.Length==0)return "-";var b=new System.Text.StringBuilder();foreach(char c in s)b.Append(((ushort)c).ToString("x4"));return b.ToString();}
    static string Decode(string s){if(s=="null")return null;if(s=="-")return "";var b=new System.Text.StringBuilder();foreach(string c in s.Split(','))b.Append((char)Convert.ToUInt16(c,16));return b.ToString();}
    static IntPtr String(Alloc alloc,IntPtr heap,IntPtr pool,string s){if(s==null)return IntPtr.Zero;IntPtr a=alloc(heap,(ulong)s.Length*2,0,261),v=alloc(heap,16,1,Bits(Marshal.ReadIntPtr(pool,40)));Check(a!=IntPtr.Zero&&v!=IntPtr.Zero,"Lookup String fixture OOM");for(int i=0;i<s.Length;i++)Marshal.WriteInt16(a,i*2,unchecked((short)s[i]));Marshal.WriteIntPtr(v,a);Marshal.WriteInt64(v,8,0);return v;}
    static string Text(IntPtr v){if(v==IntPtr.Zero)return null;IntPtr a=Marshal.ReadIntPtr(v);int n=checked((int)(Marshal.ReadInt64(a,-16)/2));var chars=new char[n];for(int i=0;i<n;i++)chars[i]=(char)Marshal.ReadInt16(a,i*2);return new string(chars);}
    public static string[] Run(string dll,string[] cases,uint[] ids,string[] names,string[] mirrorNames,string[] loaders,uint programId,uint maskField,uint aaField,uint causeOffset,uint messageOffset,uint appKey,uint loaderType,ulong loaderBytes,uint loaderRefs,string runtime=null){
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),r=IntPtr.Zero,heap=IntPtr.Zero,foreign=IntPtr.Zero;Check(m!=IntPtr.Zero,"Lookup image DLL load failed");
        try{
            if(runtime!=null){r=LoadLibraryExW(runtime,IntPtr.Zero,0x1100);Check(r!=IntPtr.Zero,"Full runtime DLL load failed");}
            var create=Fn<Create>(m,"boom_heap_create");heap=create(16777216);Check(heap!=IntPtr.Zero&&Fn<One>(m,"boom_bind_heap")(heap)==1,"Lookup heap bind failed");
            var alloc=Fn<Alloc>(m,"boom_heap_alloc");var entry=Fn<Entry>(m,"boom_entry32");var query=Fn<Service>(r==IntPtr.Zero?m:r,"boom_class_for_name");var layout=Fn<Indexed>(m,"boom_get_object_layout");IntPtr pool=Fn<Pointer>(m,"boom_get_for_name_pool")(),strings=Marshal.ReadIntPtr(pool,16),mirrors=Marshal.ReadIntPtr(pool,8),loaderPool=Marshal.ReadIntPtr(pool,32);
            var tags=new Dictionary<IntPtr,string>();for(int i=0;i<ids.Length;i++)tags[layout(ids[i])]=names[i];
            Func<IntPtr,string> type=v=>{Check(v!=IntPtr.Zero&&tags.ContainsKey(Marshal.ReadIntPtr(v,-8)),"Unknown lookup Throwable tag");return tags[Marshal.ReadIntPtr(v,-8)];};
            ulong plan=0;for(ulong i=0;i<11;i++){var w=new Context();IntPtr mirror=entry(ref w,new[]{i});Check(w.Kind==0&&mirror!=IntPtr.Zero,"Lookup mirror warmup failed: "+i+"/"+w.Kind);plan=w.Plan;}
            IntPtr mask=Fn<Field>(m,"boom_get_static_field")(programId,maskField),aa=Fn<Field>(m,"boom_get_static_field")(programId,aaField);Check(mask!=IntPtr.Zero&&Marshal.ReadInt32(mask)==0,"Class literals initialized lookup targets");
            IntPtr map=Marshal.ReadIntPtr(loaderPool,24),rows=Marshal.ReadIntPtr(map,16),loaderTag=IntPtr.Zero;for(int i=0;i<Marshal.ReadInt32(map,8);i++){IntPtr row=IntPtr.Add(rows,i*40);if((uint)Marshal.ReadInt32(row,16)==loaderType&&Marshal.ReadInt32(row,20)==0)loaderTag=Marshal.ReadIntPtr(row);}
            Check(loaderTag!=IntPtr.Zero,"Missing VM loader layout fixture");IntPtr loader=alloc(heap,loaderBytes,loaderRefs,Bits(loaderTag));for(int i=0;i<(int)loaderBytes;i++)Marshal.WriteByte(loader,i,0);Check(Fn<Bind>(m,"boom_class_loader_bind")(loaderPool,appKey,loader)==0,"VM lookup loader binding failed");
            IntPtr aaName=String(alloc,heap,strings,"dev.boom.lookup.Aa");var cold=new IntPtr[1024];System.Threading.Tasks.Parallel.For(0,8,new System.Threading.Tasks.ParallelOptions{MaxDegreeOfParallelism=8},worker=>{for(int j=0;j<128;j++){var c=new Context{Plan=plan};cold[worker*128+j]=query(ref c,new[]{Bits(aaName),1UL,Bits(loader),0UL},pool);Check(c.Kind==0&&cold[worker*128+j]!=IntPtr.Zero&&c.Depth==0,"Concurrent lookup/init failed: "+c.Kind);}});Check(new HashSet<IntPtr>(cold).Count==1&&Marshal.ReadInt32(aa)==1&&Marshal.ReadInt32(mask)==1,"Concurrent initialization/canonical mirror differs");
            var results=new List<string>();foreach(string line in cases){string[] f=line.Split(' ');IntPtr name=String(alloc,heap,strings,Decode(f[2]));var c=new Context{Plan=plan};IntPtr v=query(ref c,new[]{Bits(name),f[1]=="1"?1UL:0UL,f[0]=="0"?0UL:Bits(loader),0UL},pool);Check(c.Depth==0,"Name lookup leaked Java frames");int bits=Marshal.ReadInt32(mask);
                if(c.Kind==0){Check(v!=IntPtr.Zero&&Marshal.ReadIntPtr(v,-8)==Marshal.ReadIntPtr(mirrors,32),"Lookup did not return Class");int id=Marshal.ReadInt32(v);Check(id>=0&&id<mirrorNames.Length&&Marshal.ReadIntPtr(Marshal.ReadIntPtr(mirrors,16),id*8)==v,"Lookup mirror not canonical");results.Add("v "+Hex(mirrorNames[id])+" "+(loaders[id]=="bootstrap"?"bootstrap":loaders[id]=="platform"?"platform":"application")+" "+bits);}
                else if(c.Kind==4){Check(v==IntPtr.Zero,"Null lookup returned Class");results.Add("e java.lang.NullPointerException - - "+bits);}
                else {Check(v==IntPtr.Zero&&c.Kind==16&&c.Pending!=0,"Name lookup failure was not materialized: "+Decode(f[2])+"/"+c.Kind);IntPtr e=new IntPtr(unchecked((long)c.Pending)),cause=Marshal.ReadIntPtr(e,(int)causeOffset);string n=type(e),message=n=="java.lang.ClassNotFoundException"?Hex(Text(Marshal.ReadIntPtr(e,(int)messageOffset))):"-";if(n=="java.lang.ClassNotFoundException")Check(cause==IntPtr.Zero,"ClassNotFoundException cause must be explicitly NULL");results.Add("e "+n+" "+(cause==IntPtr.Zero||cause==e?"-":type(cause))+" "+message+" "+bits);}
            }
            foreach(string n in new[]{"java.lang.String","java.lang.Class","[[[[[[Ldev.boom.lookup.Aa;","[[[[[[I"}){IntPtr name=String(alloc,heap,strings,n);var c=new Context{Plan=plan};Check(query(ref c,new[]{Bits(name),1UL,Bits(loader),0UL},pool)==IntPtr.Zero&&c.Kind==20,"Unlinked initializer/array metadata silently simulated: "+n+"/"+c.Kind);}
            var pending=new Context{Kind=23,PC=91,Method=37,Depth=2,Pending=0x1234,Plan=0x5678};Check(query(ref pending,null,IntPtr.Zero)==IntPtr.Zero&&pending.Kind==23&&pending.PC==91&&pending.Method==37&&pending.Depth==2&&pending.Pending==0x1234&&pending.Plan==0x5678,"Pending lookup context changed");
            foreign=create(4096);IntPtr bad=String(alloc,foreign,strings,"dev.boom.lookup.Aa");var raw=new Context{Plan=plan};Check(query(ref raw,new[]{Bits(bad),0UL,Bits(loader),0UL},pool)==IntPtr.Zero&&raw.Kind==7,"Foreign String accepted");
            bad=alloc(heap,8,0,267);raw=new Context{Plan=plan};Check(query(ref raw,new[]{Bits(bad),0UL,Bits(loader),0UL},pool)==IntPtr.Zero&&raw.Kind==7,"Wrong name type accepted");
            raw=new Context{Plan=plan};Check(query(ref raw,new[]{Bits(aaName),0UL,Bits(bad),0UL},pool)==IntPtr.Zero&&raw.Kind==7,"Wrong loader type accepted");
            IntPtr unbound=alloc(heap,loaderBytes,loaderRefs,Bits(loaderTag));for(int i=0;i<(int)loaderBytes;i++)Marshal.WriteByte(unbound,i,0);raw=new Context{Plan=plan};Check(query(ref raw,new[]{Bits(aaName),0UL,Bits(unbound),0UL},pool)==IntPtr.Zero&&raw.Kind==20,"Unbound loader identity was guessed");
            raw=new Context{Plan=plan};Check(query(ref raw,new[]{Bits(aaName),0UL,Bits(loader),Bits(bad)},pool)==IntPtr.Zero&&raw.Kind==7,"Wrong caller type accepted");
            IntPtr badPool=Marshal.AllocHGlobal(96);try{byte[] bytes=new byte[96];Marshal.Copy(pool,bytes,0,96);Marshal.Copy(bytes,0,badPool,96);Marshal.WriteInt32(badPool,76,1);raw=new Context{Plan=plan};Check(query(ref raw,new[]{Bits(aaName),0UL,Bits(loader),0UL},badPool)==IntPtr.Zero&&raw.Kind==7,"Bad lookup metadata accepted");}finally{Marshal.FreeHGlobal(badPool);}
            GC(m,heap,aaName);IntPtr missing=String(alloc,heap,strings,"dev.boom.lookup.Missing");while(alloc(heap,4096,0,267)!=IntPtr.Zero){}while(alloc(heap,0,0,267)!=IntPtr.Zero){}long full=Marshal.ReadInt64(heap,56);raw=new Context{Plan=plan};Check(query(ref raw,new[]{Bits(aaName),0UL,Bits(loader),0UL},pool)==cold[0]&&raw.Kind==0&&Marshal.ReadInt64(heap,56)==full,"Hot lookup allocated at full heap");raw=new Context{Plan=plan};Check(query(ref raw,new[]{Bits(missing),0UL,Bits(loader),0UL},pool)==IntPtr.Zero&&raw.Kind==3&&Marshal.ReadInt64(heap,56)==full,"Missing-class OOM collected automatically");GC(m,heap,aaName,missing);raw=new Context{Plan=plan};Check(query(ref raw,new[]{Bits(missing),0UL,Bits(loader),0UL},pool)==IntPtr.Zero&&raw.Kind==16&&raw.Pending!=0,"Lookup error did not recover after explicit collection");GC(m,heap,new IntPtr(unchecked((long)raw.Pending)));
            return results.ToArray();
        }finally{if(m!=IntPtr.Zero)Check(Fn<Release>(m,"boom_release_trace_pool")()==0,"Lookup Java frames remain");if(foreign!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(foreign);if(heap!=IntPtr.Zero)Fn<One>(m,"boom_heap_destroy")(heap);if(r!=IntPtr.Zero)FreeLibrary(r);if(m!=IntPtr.Zero)FreeLibrary(m);}
    }
}
