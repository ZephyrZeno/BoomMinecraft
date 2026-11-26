using System;
using System.Runtime.InteropServices;

public static class BoomAssemblyObjectCacheProbe
{
    [UnmanagedFunctionPointer(CallingConvention.Winapi)]
    private delegate ulong Value();

    public static void Check(string path, ulong expected)
    {
        IntPtr library = NativeLibrary.Load(path);
        try
        {
            var entry = Marshal.GetDelegateForFunctionPointer<Value>(
                NativeLibrary.GetExport(library, "boom_cache_value"));
            ulong actual = entry();
            if (actual != expected)
                throw new InvalidOperationException("Cached machine code returned " + actual + ", expected " + expected);
        }
        finally { NativeLibrary.Free(library); }
    }
}
