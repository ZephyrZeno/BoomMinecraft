using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading.Tasks;

// Source Java constructor/override and ASM identities. Array allocation is a VM fixture.
public static class BoomNormalIdentityProviderProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong n);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Bind(IntPtr h);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Ensure(IntPtr cls,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr New(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Alloc(IntPtr heap,ulong bytes,ulong refs,ulong tag);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Literal(IntPtr ctx,IntPtr pool,uint id);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Entry(IntPtr ctx,IntPtr args);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Service(IntPtr ctx,IntPtr args,IntPtr pool,int op);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Release();
    static T Fn<T>(IntPtr lib,string n) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(lib,n));}
    static void Need(bool ok,string message){if(!ok)throw new Exception(message);}
    static IntPtr Memory(List<IntPtr> list,int bytes){var p=Marshal.AllocHGlobal(bytes);for(int i=0;i<bytes;i++)Marshal.WriteByte(p,i,0);list.Add(p);return p;}
    static void Reset(IntPtr c){for(int i=0;i<32;i+=8)Marshal.WriteInt64(c,i,0);}
    public static long[] Run(string runtime,string image,int objectId,int classId,int systemId,string ctorName,string stringHashName,string objectHashName,string identityName,uint literalId,ushort[] text,int[] arrayIds,long[] primitiveTags,int[] shifts,int[] kinds){
        IntPtr lib=NativeLibrary.Load(runtime),dll=NativeLibrary.Load(image),heap=IntPtr.Zero;var owned=new List<IntPtr>();var destroy=Fn<Destroy>(lib,"boom_heap_destroy");
        try {
            var ctx=Memory(owned,32);var args=Memory(owned,8);heap=Fn<Create>(lib,"boom_heap_create")(128UL*1024*1024);
            Need(heap!=IntPtr.Zero&&Fn<Bind>(dll,"boom_java_string_literals_bind_heap")(heap)==1,"Identity heap binding failed");
            var ensure=Fn<Ensure>(lib,"boom_class_ensure32");
            foreach(int id in new[]{classId,objectId,systemId})Need(ensure(NativeLibrary.GetExport(dll,"boom_class"+id),ctx)==0&&Marshal.ReadInt32(ctx)==0,"Original identity declaring class init failed");
            var create=Fn<New>(lib,"boom_object_new");var ctor=Fn<Entry>(dll,ctorName);var objectHash=Fn<Entry>(dll,objectHashName);var identity=Fn<Entry>(dll,identityName);
            var objects=new List<IntPtr>();IntPtr layout=NativeLibrary.GetExport(dll,"boom_layout"+objectId);
            for(int i=0;i<256;i++){IntPtr obj=create(heap,layout,ctx);Need(obj!=IntPtr.Zero,"Object allocation failed");Marshal.WriteIntPtr(args,obj);ctor(ctx,args);Need(Marshal.ReadInt32(ctx)==0,"Original Object constructor failed");objects.Add(obj);}
            var allocate=Fn<Alloc>(lib,"boom_heap_alloc");var descriptors=NativeLibrary.GetExport(dll,"boom_batch_type_descriptors");
            for(int i=0;i<arrayIds.Length;i++){
                long tag=primitiveTags[i]>=0?primitiveTags[i]:Marshal.ReadIntPtr(descriptors,checked(arrayIds[i]*8)).ToInt64();int bytes=8<<shifts[i];
                IntPtr array=allocate(heap,(ulong)bytes,kinds[i]==2?8UL:0UL,unchecked((ulong)tag));Need(array!=IntPtr.Zero,"Typed array fixture allocation failed");
                for(int j=0;j<bytes;j++)Marshal.WriteByte(array,j,0);objects.Add(array);
            }
            IntPtr str=Fn<Literal>(dll,"boom_java_string_literal")(ctx,NativeLibrary.GetExport(dll,"boom_java_string_literal_pool"),literalId);
            Need(str!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Normal source String literal failed");objects.Add(str);
            var hashes=new List<ulong>();var distinct=new HashSet<ulong>();
            foreach(IntPtr obj in objects){Marshal.WriteIntPtr(args,obj);ulong h=objectHash(ctx,args);Need(h!=0&&h<=int.MaxValue&&Marshal.ReadInt32(ctx)==0&&identity(ctx,args)==h,"Source default/System identity disagreement");hashes.Add(h);distinct.Add(h);}
            Need(distinct.Count>128,"Identity distribution collapsed for distinct live objects");
            var stringHash=Fn<Entry>(dll,stringHashName);int expected=0;foreach(ushort c in text)expected=unchecked(expected*31+c);
            Marshal.WriteIntPtr(args,str);Need(unchecked((int)stringHash(ctx,args))==expected&&Marshal.ReadInt32(ctx)==0,"Original String.hashCode override changed");
            Marshal.WriteInt32(objects[256],0,12345);Marshal.WriteIntPtr(args,objects[256]);Need(identity(ctx,args)==hashes[256],"Array payload mutation changed identity");
            var service=Fn<Service>(dll,"boom_provider_identity_service");var profile=NativeLibrary.GetExport(dll,"boom_provider_identity_pool");var copy=Memory(owned,32);byte[] bytes_=new byte[32];Marshal.Copy(profile,bytes_,0,32);int checks=0;
            Marshal.WriteIntPtr(args,IntPtr.Zero);Need(identity(ctx,args)==0&&Marshal.ReadInt32(ctx)==0,"System identity(null) failed");checks++;
            Need(objectHash(ctx,args)==0&&Marshal.ReadInt32(ctx)==4,"Object null receiver did not produce NPE");checks++;Reset(ctx);
            foreach(int offset in new[]{0,4,8,12,16,24}){Marshal.Copy(bytes_,0,copy,32);if(offset==16||offset==24)Marshal.WriteIntPtr(copy,offset,IntPtr.Zero);else Marshal.WriteInt32(copy,offset,123);
                Need(service(ctx,args,copy,1)==0&&Marshal.ReadInt32(ctx)==7,"Invalid identity profile accepted: "+offset);checks++;Reset(ctx);}
            foreach(IntPtr invalid in new[]{new IntPtr(1),IntPtr.Add(objects[0],1)}){Marshal.WriteIntPtr(args,invalid);Need(service(ctx,args,profile,1)==0&&Marshal.ReadInt32(ctx)==7,"Foreign/interior identity reference accepted");checks++;Reset(ctx);}
            Marshal.WriteIntPtr(args,objects[0]);Need(service(ctx,args,profile,2)==0&&Marshal.ReadInt32(ctx)==7,"Unknown identity operation accepted");checks++;Reset(ctx);
            Marshal.WriteInt32(ctx,66);Need(service(ctx,args,copy,1)==0&&Marshal.ReadInt32(ctx)==66,"Pending identity error overwritten");checks++;Reset(ctx);
            const int workers=8,iterations=1024;long before=Marshal.ReadInt64(heap,48);
            Parallel.For(0,workers,w=>{IntPtr c=Marshal.AllocHGlobal(32),a=Marshal.AllocHGlobal(8);try{Reset(c);for(int i=0;i<iterations;i++){int at=(w+i)%objects.Count;Marshal.WriteIntPtr(a,objects[at]);Need(objectHash(c,a)==hashes[at]&&identity(c,a)==hashes[at]&&Marshal.ReadInt32(c)==0,"Concurrent identity changed");}}finally{Marshal.FreeHGlobal(a);Marshal.FreeHGlobal(c);}});
            Need(Marshal.ReadInt64(heap,48)==before,"Warm identity queries allocated guest memory");
            Need(Marshal.ReadInt32(NativeLibrary.GetExport(dll,"boom_diagnostic_pool"),8)==0,"Identity source test reached an unsupported dependency");
            return new long[]{objects.Count,distinct.Count,checks,workers,workers*iterations*2,256};
        } finally {
            Need(Fn<Release>(dll,"boom_release_trace_pool")()==0,"Identity image retained Java frames");
            if(heap!=IntPtr.Zero)Need(destroy(heap)==1,"Identity heap cleanup failed");foreach(var p in owned)Marshal.FreeHGlobal(p);NativeLibrary.Free(dll);NativeLibrary.Free(lib);
        }
    }
}
