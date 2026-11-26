import jdk.internal.misc.CDS;

// Development oracle only. Run with -Xshare:off, never as a guest fallback.
public class NormalCdsReference {
    static int initialized;
    static class Cold { static int value=initialize(); static int initialize(){ initialized++; return 731; } }
    public static void main(String[] args) throws Exception {
        if(CDS.isDumpingClassList() || CDS.isDumpingArchive() || CDS.isSharingEnabled()) throw new AssertionError("CDS must be disabled");
        if(CDS.getRandomSeedForDumping()!=0) throw new AssertionError("Non-dumping seed differs");
        Class<?> cold=Class.forName(NormalCdsReference.class.getName()+"$Cold",false,NormalCdsReference.class.getClassLoader());
        if(initialized!=0) throw new AssertionError("Cold class initialized early");
        CDS.initializeFromArchive(cold);
        if(initialized!=0) throw new AssertionError("No-archive initialization initialized target");
        if(Cold.value!=731 || initialized!=1) throw new AssertionError("Java initializer not executed");
        CDS.initializeFromArchive(cold);
        if(Cold.value!=731 || initialized!=1) throw new AssertionError("No-archive call changed initialized state");
        System.out.println("flags=0,0,0 seed=0 cold_target_preserved=true Java_initializer_executed=true");
    }
}
