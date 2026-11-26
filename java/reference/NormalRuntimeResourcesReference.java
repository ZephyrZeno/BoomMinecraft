/** JVM development oracle; the native runtime has its own heap budget. */
public class NormalRuntimeResourcesReference {
    public static void main(String[] args) {
        Runtime r=Runtime.getRuntime();
        long free=r.freeMemory(),total=r.totalMemory(),max=r.maxMemory();
        if(free<0 || total<=0 || max<total || free>total)throw new AssertionError("memory counters");
        System.out.println("cpu\t"+r.availableProcessors());
        System.out.println("memory_invariants\ttrue");
    }
}
