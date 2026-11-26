package dev.boom.subset;

/** Primitive-array bytecode fixtures. Heap services are the assembly runtime. */
public final class ArrayKernels {
    public static int intArray(int n,int seed) { int[] a=new int[n];for(int i=0;i<n;i++)a[i]=seed+i*31;int result=0;for(int i=0;i<a.length;i++)result^=a[i];return result; }
    public static long longArray(int n,long seed) { long[] a=new long[n];for(int i=0;i<n;i++)a[i]=seed+i*0x123456789abcdefL;long sum=0;for(int i=0;i<a.length;i++)sum^=a[i];return sum; }
    public static float floatArray(int n,float seed) { float[] a=new float[n];for(int i=0;i<n;i++)a[i]=seed+i*0.125f;float sum=0;for(int i=0;i<a.length;i++)sum+=a[i];return sum; }
    public static double doubleArray(int n,double seed) { double[] a=new double[n];for(int i=0;i<n;i++)a[i]=seed+i*0.125;double sum=0;for(int i=0;i<a.length;i++)sum+=a[i];return sum; }
    public static int byteArray(int n,int seed) { byte[] a=new byte[n];for(int i=0;i<n;i++)a[i]=(byte)(seed+i);int sum=0;for(int i=0;i<a.length;i++)sum+=a[i];return sum; }
    public static int charArray(int n,int seed) { char[] a=new char[n];for(int i=0;i<n;i++)a[i]=(char)(seed+i);int sum=0;for(int i=0;i<a.length;i++)sum+=a[i];return sum; }
    public static int shortArray(int n,int seed) { short[] a=new short[n];for(int i=0;i<n;i++)a[i]=(short)(seed+i);int sum=0;for(int i=0;i<a.length;i++)sum+=a[i];return sum; }
    public static int booleanArray(int n,int seed) { boolean[] a=new boolean[n];for(int i=0;i<n;i++)a[i]=((seed>>>i)&1)!=0;int sum=0;for(int i=0;i<a.length;i++)if(a[i])sum++;return sum; }
    public static int literalArray(int seed) { int[] a={seed,seed+1,seed+2};return a[0]^a[1]^a[2]; }
    private static int[] build(int n,int seed) { int[] a=new int[n];for(int i=0;i<n;i++)a[i]=seed-i;return a; }
    private static int sum(int[] a) { int result=0;for(int i=0;i<a.length;i++)result+=a[i];return result; }
    public static int arrayCalls(int n,int seed) { return sum(build(n,seed)); }
    public static int nullMerge(int n) { int[] a=null;if(n>0)a=new int[n];return a.length; }
    public static int nullBranch(int n) { int[] a=n>0?new int[n]:null;if(a==null)return -7;if(a!=null)return a.length;return 0; }
    public static int nullViaCall(int n) { return sum(n==0?null:new int[n]); }
    public static int referenceCompare(int n) { int[] a=new int[n];int[] b=a;int[] c=new int[n];return a==b&&a!=c?1:0; }
    public static int bounds(int n,int index) { int[] a=new int[n];a[index]=17;return a[index]; }
    public static int compound(int n,int seed) { int[] a=new int[n];for(int i=0;i<n;i++)a[i]+=seed+i;return sum(a); }
}
