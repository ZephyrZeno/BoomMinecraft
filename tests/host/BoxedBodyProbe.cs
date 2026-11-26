using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;

// Executes unmodified original JDK constructor/accessor translations against
// generated source layouts and field maps. Class initialization is not run.
public static class BoomBoxedBodyProbe {
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Create(ulong size);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Destroy(IntPtr heap);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Make(IntPtr heap,IntPtr layout,IntPtr ctx);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate ulong Body(IntPtr ctx,IntPtr argv);
    sealed class Type {public IntPtr Layout;public Body Constructor,Getter;}
    sealed class Case {public string Name;public ulong Bits,Expected;}
    static T Symbol<T>(IntPtr module,string name) where T:Delegate{return Marshal.GetDelegateForFunctionPointer<T>(NativeLibrary.GetExport(module,name));}
    static void Need(bool value,string message){if(!value)throw new Exception(message);}
    public static long[] Run(string runtime,string generated,string directory) {
        IntPtr native=NativeLibrary.Load(runtime),module=IntPtr.Zero,heap=IntPtr.Zero;
        Destroy destroy=Symbol<Destroy>(native,"boom_heap_destroy");
        try{
            module=NativeLibrary.Load(generated);
            var types=new Dictionary<string,Type>();IntPtr map=NativeLibrary.GetExport(module,"boom_runtime_type_map"),rows=Marshal.ReadIntPtr(map,16);
            foreach(string line in File.ReadLines(Path.Combine(directory,"boxed-types.tsv"))) {
                string[] p=line.Split('\t');int id=int.Parse(p[1]);IntPtr layout=IntPtr.Zero;
                for(int i=0;i<Marshal.ReadInt32(map,8);i++)if(Marshal.ReadInt32(rows,i*40+16)==id){layout=Marshal.ReadIntPtr(rows,i*40);break;}
                Need(layout!=IntPtr.Zero,"Missing boxed source layout");
                types[p[0]]=new Type{Layout=layout,Constructor=Symbol<Body>(module,p[2]),Getter=Symbol<Body>(module,p[3])};
            }
            string[] expected=File.ReadAllLines(Path.Combine(directory,"boxed-oracle.tsv"));var cases=new List<Case>();
            foreach(string line in File.ReadLines(Path.Combine(directory,"boxed-cases.tsv"))) {
                string[] p=line.Split('\t');cases.Add(new Case{Name=p[0],Bits=ulong.Parse(p[1],NumberStyles.HexNumber),Expected=ulong.Parse(expected[cases.Count],NumberStyles.HexNumber)});
            }
            Need(cases.Count==expected.Length,"Boxed JVM case count differs");
            heap=Symbol<Create>(native,"boom_heap_create")(4*1024*1024);Need(heap!=IntPtr.Zero,"Boxed body heap creation failed");
            Make make=Symbol<Make>(native,"boom_object_new");
            Parallel.For(0,8,worker=>{
                IntPtr ctx=Marshal.AllocHGlobal(32),args=Marshal.AllocHGlobal(16);
                try{for(int i=0;i<32;i++)Marshal.WriteByte(ctx,i,0);
                    for(int index=worker;index<cases.Count;index+=8){Case c=cases[index];Type type=types[c.Name];
                        IntPtr value=make(heap,type.Layout,ctx);Need(value!=IntPtr.Zero&&Marshal.ReadInt32(ctx)==0,"Boxed allocation failed");
                        Marshal.WriteIntPtr(args,value);Marshal.WriteInt64(args,8,unchecked((long)c.Bits));
                        Need(type.Constructor(ctx,args)==0&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt32(ctx,12)==0,"Original constructor body failed: "+c.Name);
                        ulong actual=type.Getter(ctx,args);
                        Need(actual==c.Expected&&Marshal.ReadInt32(ctx)==0&&Marshal.ReadInt32(ctx,12)==0,"Original accessor body differs: "+c.Name+"/"+c.Bits.ToString("x"));
                    }
                }finally{Marshal.FreeHGlobal(args);Marshal.FreeHGlobal(ctx);}
            });
            GC.KeepAlive(make);GC.KeepAlive(types);
            return new long[]{types.Count,cases.Count,cases.Count*2L,8};
        }finally{if(heap!=IntPtr.Zero)destroy(heap);if(module!=IntPtr.Zero)NativeLibrary.Free(module);NativeLibrary.Free(native);GC.KeepAlive(destroy);}
    }
}
