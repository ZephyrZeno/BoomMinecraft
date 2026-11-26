package dev.boom.link;
public final class LinkArrays {
    public static int[] create(int n) { return new int[n]; }
    public static void fill(int[] data,int seed) { LinkInts.fill(data,seed); }
    public static int sum(int[] data) { int sum=0;for(int i=0;i<data.length;i++)sum+=data[i];return sum; }
    public static int mutate(int[] data,int seed) { data[0]^=seed;return data[data.length-1]; }
    public static int at(int[] data,int index) { return data[index]; }
}
