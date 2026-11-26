import java.lang.reflect.Field;
import java.lang.reflect.Method;

/** JVM development oracle; never part of the assembly game runtime. */
public class NormalUnsafeBootstrapReference {
    public static void main(String[] args) throws Exception {
        Class<?> c = Class.forName("jdk.internal.misc.Unsafe");
        Field f = c.getDeclaredField("theUnsafe"); f.setAccessible(true);
        Object u = f.get(null);
        System.out.println("ADDRESS_SIZE0\t" + c.getMethod("addressSize").invoke(u));
        System.out.println("PAGE_SIZE\t" + c.getMethod("pageSize").invoke(u));
        Class<?> constants = Class.forName("jdk.internal.misc.UnsafeConstants");
        for (String n : new String[]{"BIG_ENDIAN", "UNALIGNED_ACCESS"}) {
            Field value = constants.getDeclaredField(n); value.setAccessible(true);
            System.out.println(n + "\t" + value.get(null));
        }
        Method scale = c.getMethod("arrayIndexScale", Class.class);
        for (Class<?> array : new Class<?>[]{boolean[].class, byte[].class, short[].class, char[].class,
                int[].class, long[].class, float[].class, double[].class})
            System.out.println(array.getName() + "\t" + scale.invoke(u, array));
        c.getMethod("fullFence").invoke(u);
    }
}
