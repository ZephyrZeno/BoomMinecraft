package dev.boom.link;
public final class LinkInts {
    public static int mix(int a,int b) { return LinkEntry.callback(a*31+b); }
    public static short narrow(int a) { return (short)a; }
    public static int divide(int a,int b) { return a/b; }
    public static void fill(int[] data,int seed) { for(int i=0;i<data.length;i++)data[i]=seed+i; }
    public static int overload(int a) { return (a<<7)^(a>>>25); }
    public static long overload(long a) { return (a<<17)^(a>>>47); }
    public static int recursive(int a) { return LinkEntry.recursive(a-1); }
}
