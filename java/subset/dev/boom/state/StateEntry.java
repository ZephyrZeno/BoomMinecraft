package dev.boom.state;

public final class StateEntry {
    public static int constants(int seed) { return Constants.dynamic+seed; }
    public static long longValue(long seed) { return Numbers.wide^seed; }
    public static float floatValue(float seed) { return Numbers.single+seed; }
    public static double doubleValue(double seed) { return Numbers.real*seed; }
    public static int narrow(int seed) { return Numbers.small+Numbers.signed+Numbers.letter+(Numbers.flag?17:0)+seed; }
    public static int table(int index,int seed) { return Table.values[index]^seed^Table.runs; }
    public static int cycle(int seed) { return CycleA.value*31+CycleB.value+seed; }
    public static int reentry(int seed) { return Reentry.value^seed; }
    public static int failure() { return Failure.value; }
    public static int failureArray() { return FailureArray.value; }
    public static int failureOom() { return FailureOom.values.length; }
    public static int failureNested() { return FailureParent.value; }
    public static int counter(int seed) { return Counter.next()+seed; }
    public static int race(int seed) { return (Race.runs<<24)^(Race.published&0xffffff)^seed; }
    public static int volatileField() { return UnsupportedVolatile.value; }
    public static int objectField() { return UnsupportedObject.value==null?0:1; }
}
final class Constants {
    static final int I=0x89abcdef;
    static final long J=Long.MIN_VALUE;
    static final float F=-0.0f;
    static final double D=Double.NaN;
    static final boolean Z=true;
    static final byte B=-113;
    static final short S=-12345;
    static final char C=0xffe1;
    static int dynamic=I+(int)J+(Z?B:0)+S+C;
}
final class Numbers {
    static long wide=0xfedcba9876543210L;
    static float single=-0.0f;
    static double real=-1.0000000000000002;
    static short small=-12345;
    static byte signed=-113;
    static char letter=0xffe1;
    static boolean flag=true;
}
final class Table {
    static int runs;
    static final int[] values=create();
    static int[] alias=values;
    static int[] create() { runs++;int[] a=new int[32];for(int i=0;i<a.length;i++)a[i]=i*1664525+1013904223;return a; }
}
final class CycleA { static int value=CycleB.value+1; }
final class CycleB { static int value=CycleA.value+2; }
final class Reentry {
    static int value=calculate()+3;
    static int calculate() { return value+5; }
}
final class Failure {
    static int zero;
    static int value=11/zero;
}
final class FailureArray {
    static int[] retained=new int[7];
    static int zero;
    static int value=11/zero;
}
final class FailureOom { static int[] values=new int[Integer.MAX_VALUE]; }
final class FailureInner { static int zero;static int value=11/zero; }
final class FailureParent { static int value=FailureInner.value; }
final class Counter {
    static int count;
    static { count++; }
    static int next() { return ++count; }
}
final class Race {
    static int runs;
    static int published;
    static {
        runs++;
        int sum=123;
        for(int i=0;i<2000000;i++)sum=(sum*1664525+1013904223)^(sum>>>13);
        published=sum;
    }
}
final class UnsupportedVolatile { static volatile int value; }
final class UnsupportedObject { static Object value=new Object(); }
