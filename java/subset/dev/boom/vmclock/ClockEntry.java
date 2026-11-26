package dev.boom.vmclock;
public final class ClockEntry {
    static volatile int sink;
    public static long millis(int ignored) {return System.currentTimeMillis();}
    public static long nanos(int ignored) {return System.nanoTime();}
    public static long monotonic(int count) {
        long previous=System.nanoTime();
        for(int i=0;i<count;i++){long next=System.nanoTime();if(next<previous)return 0;previous=next;}
        return 1;
    }
    public static long elapsed(int count) {
        long start=System.nanoTime();int value=17;
        for(int i=0;i<count;i++)value=value*1664525+1013904223;
        sink=value;
        return System.nanoTime()-start;
    }
}
