package dev.boom.link;
public final class LinkEntry {
    public static int intRoot(int a,int b) { return LinkInts.mix(a,b)^Hidden.twice(a); }
    public static int callback(int a) { return a^0x5a5a5a5a; }
    public static long longRoot(long seed,int count) { for(int i=0;i<count;i++)seed=LinkNumbers.step(seed,i);return seed; }
    public static float floatRoot(float a,float b,float c) { return LinkNumbers.mix(a,b,c); }
    public static double doubleRoot(double a,double b) { return LinkNumbers.mix(a,b)+(double)LinkInts.narrow((int)a); }
    public static int divide(int a,int b) { return LinkInts.divide(a,b)+1; }
    public static int arrayRoot(int n,int seed) { int[] data=LinkArrays.create(n);LinkInts.fill(data,seed);return LinkArrays.sum(data); }
    public static int arrayAlias(int n,int seed) { int[] data=LinkArrays.create(n);LinkArrays.fill(data,seed);return LinkArrays.mutate(data,seed)^LinkArrays.sum(data); }
    public static int arrayFault(int n,int index) { return LinkArrays.at(LinkArrays.create(n),index); }
    public static float floatArray(int n,float seed) { return LinkNumbers.sum(LinkNumbers.create(n,seed)); }
    public static int overload(int a) { return LinkInts.overload(a); }
    public static long overload(long a) { return LinkInts.overload(a); }
    public static int recursive(int a) { return LinkInts.recursive(a); }
    public static int initialized(int a) { return LinkInitialized.identity(a); }
    public static int objectReference() { return LinkObjects.unsafe(); }
    public static void noState() { }
}
final class Hidden { static int twice(int a) { return a*2; } }
