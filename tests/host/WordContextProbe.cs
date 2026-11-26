// Controller only. DFA/category lookup and Unicode properties execute MASM.
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
public static class BoomWordContextProbe {
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] static extern IntPtr LoadLibraryExW(string p,IntPtr z,uint f);
    [DllImport("kernel32.dll",CharSet=CharSet.Ansi)] static extern IntPtr GetProcAddress(IntPtr m,string n);
    [DllImport("kernel32.dll")] static extern bool FreeLibrary(IntPtr m);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate IntPtr Pointer();
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Next(IntPtr chars,int length,int index,IntPtr pool);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate uint Context(uint cp);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Boundary(IntPtr chars,int length,int index,IntPtr pool,ref int cache);
    static void Check(bool v,string why) { if(!v) throw new Exception(why); }
    static T Fn<T>(IntPtr m,string n) { IntPtr p=GetProcAddress(m,n); Check(p!=IntPtr.Zero,"Missing "+n);return Marshal.GetDelegateForFunctionPointer<T>(p); }
    public static string ContextHash(string dll) {
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100);Check(m!=IntPtr.Zero,"Context runtime load failed");
        try { var context=Fn<Context>(m,"boom_unicode_context");var bytes=new byte[0x220000];
            for(uint cp=0;cp<0x110000;cp++) { uint value=context(cp);Check(value<=511,"Invalid context property word");bytes[cp*2]=(byte)value;bytes[cp*2+1]=(byte)(value>>8); }
            Check(context(0x110000)==0&&context(uint.MaxValue)==0,"Out-of-range Unicode context not empty");
            using(var hash=SHA256.Create())return BitConverter.ToString(hash.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();
        } finally {FreeLibrary(m);}
    }
    public static string[] Boundaries(string dll,string[] cases,bool queries=false) {
        IntPtr m=LoadLibraryExW(dll,IntPtr.Zero,0x1100),copy=IntPtr.Zero;Check(m!=IntPtr.Zero,"Word runtime load failed");
        try {
            IntPtr plan=Fn<Pointer>(m,"boom_get_word_plan")();var next=Fn<Next>(m,"boom_word_next");var result=new List<string>();
            foreach(string line in cases) {
                string[] units=line=="-"?new string[0]:line.Split(',');IntPtr chars=Marshal.AllocHGlobal(Math.Max(2,units.Length*2));
                try {
                    for(int i=0;i<units.Length;i++)Marshal.WriteInt16(chars,i*2,unchecked((short)Convert.ToUInt16(units[i],16)));
                    int index=0;var boundaries=new StringBuilder("0");
                    while(index<units.Length) {int found=next(chars,units.Length,index,plan);Check(found>index&&found<=units.Length,"DFA failed to advance: "+index+"/"+found+" in "+line);boundaries.Append(',').Append(found);index=found;}
                    Check(next(chars,units.Length,units.Length,plan)==-1,"DFA did not finish at text end");result.Add(boundaries.ToString());
                    if(queries) {
                        var boundary=Fn<Boundary>(m,"boom_word_is_boundary");boundaries.Append('|');
                        for(int order=0;order<3;order++) {if(order!=0)boundaries.Append('|');int cache=-1;
                            for(int i=0;i<=units.Length;i++) {if(order==1)cache=-1;int found=boundary(chars,units.Length,order==2?units.Length-i:i,plan,ref cache);Check(found==0||found==1,"Boundary query metadata/view failed");boundaries.Append(found);}
                        }
                        result[result.Count-1]=boundaries.ToString();
                    }
                    Check(next(chars,-1,0,plan)==-1&&next(chars,units.Length,-1,plan)==-1,"Invalid view bounds accepted");
                } finally {Marshal.FreeHGlobal(chars);}
            }
            copy=Marshal.AllocHGlobal(96);var raw=new byte[96];Marshal.Copy(plan,raw,0,96);Marshal.Copy(raw,0,copy,96);Marshal.WriteInt32(copy,76,1);
            IntPtr one=Marshal.AllocHGlobal(2);try {Marshal.WriteInt16(one,65);Check(next(one,1,0,copy)==-1,"Nonzero reserved metadata accepted");Marshal.Copy(raw,0,copy,96);Marshal.WriteIntPtr(copy,16,IntPtr.Zero);Check(next(one,1,0,copy)==-1,"Null state table accepted");}finally{Marshal.FreeHGlobal(one);}
            return result.ToArray();
        } finally {if(copy!=IntPtr.Zero)Marshal.FreeHGlobal(copy);FreeLibrary(m);}
    }
}
