package dev.boom.cds;
import jdk.internal.misc.CDS;

public final class CdsEntry {
    static final class Trace { static volatile int calls; }
    static final class Target { static int value; static { Trace.calls++; value=37; } }
    public static int run(int n) {
        Trace.calls=0;
        CDS.initializeFromArchive(Target.class);
        int flags=(CDS.isDumpingClassList()?1:0)|(CDS.isDumpingArchive()?2:0)|(CDS.isSharingEnabled()?4:0);
        return n+(flags<<16)+(int)CDS.getRandomSeedForDumping()+Trace.calls*1024;
    }
    public static int initialized(int n) {
        int before=Target.value;
        CDS.initializeFromArchive(Target.class);
        return n+before+Target.value;
    }
    public static int array(int n) { CDS.initializeFromArchive(Target[].class); return n; }
    public static int repeated(int n) {
        for(int i=0;i<7;i++) CDS.initializeFromArchive(Target.class);
        return n+(int)CDS.getRandomSeedForDumping();
    }
    public static void unsupported() { CDS.defineArchivedModules(null,null); }
}
