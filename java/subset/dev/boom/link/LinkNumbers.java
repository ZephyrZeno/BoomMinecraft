package dev.boom.link;
public final class LinkNumbers {
    public static long step(long seed,int i) { return (seed*6364136223846793005L+i)^(seed>>>17); }
    public static float mix(float a,float b,float c) { return (a+b)*c; }
    public static double mix(double a,double b) { return (a-b)/(a+b); }
    public static float[] create(int n,float seed) { float[] data=new float[n];for(int i=0;i<n;i++)data[i]=seed+i;return data; }
    public static float sum(float[] data) { float total=0;for(int i=0;i<data.length;i++)total+=data[i];return total; }
}
