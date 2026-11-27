import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.concurrent.atomic.AtomicLong;

/** Development JVM oracle only; never linked into the guest runtime. */
public final class AtomicLongCasReference {
    public static void main(String[] args) throws Exception {
        Method method = AtomicLong.class.getDeclaredMethod("VMSupportsCS8");
        Field field = AtomicLong.class.getDeclaredField("VM_SUPPORTS_LONG_CAS");
        method.setAccessible(true);
        field.setAccessible(true);
        boolean supports = (Boolean) method.invoke(null);
        for (int i = 0; i < 32; ++i) {
            if ((Boolean) method.invoke(null) != supports)
                throw new AssertionError("Capability changed");
        }
        System.out.println("supports=" + supports);
        System.out.println("cached=" + field.getBoolean(null));
        System.out.println("native_modifiers=" + method.getModifiers());
        System.out.println("field_modifiers=" + field.getModifiers());
        System.out.println("primitive_boolean=" + (method.getReturnType() == boolean.class));
        System.out.println("parameter_count=" + method.getParameterCount());
    }
}
