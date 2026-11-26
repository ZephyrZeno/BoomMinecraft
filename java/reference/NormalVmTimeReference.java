import java.lang.reflect.Method;

/** Development clock oracle; never included in the assembly game runtime. */
public class NormalVmTimeReference {
    public static void main(String[] args) throws Exception {
        Method time=Class.forName("jdk.internal.misc.VM").getMethod("getNanoTimeAdjustment",long.class);
        for(int i=0;i<16;i++)System.out.printf("v %016x%n",(long)time.invoke(null,0L));
        if((long)time.invoke(null,Long.MIN_VALUE)!=-1 || (long)time.invoke(null,Long.MAX_VALUE)!=-1)throw new AssertionError("far offset");
    }
}
