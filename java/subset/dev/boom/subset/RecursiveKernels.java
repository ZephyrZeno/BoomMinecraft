package dev.boom.subset;
public final class RecursiveKernels {
    public static int sum(int n) { return n<=0?0:sum(n-1)+n; }
    public static int fibonacci(int n) { return n<=1?n:fibonacci(n-1)+fibonacci(n-2); }
    public static long longRecursive(long seed,int count) { return count<=0?seed:(longRecursive(seed+17,count-1)*3)^seed; }
    public static int arrayRecursive(int n,int seed) {
        int[] data=new int[n];for(int i=0;i<n;i++)data[i]=seed+i;return arraySum(data,n-1);
    }
    private static int arraySum(int[] data,int index) { return index<0?0:data[index]+arraySum(data,index-1); }
    public static int throwRecursive(int n,int divisor) { return n<=0?17/divisor:throwRecursive(n-1,divisor)+1; }
    public static int runaway(int n) { return runaway(n+1); }
}
