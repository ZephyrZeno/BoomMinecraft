import dev.boom.loading.LoaderIdentity;
import java.lang.reflect.Method;

// Locked JVM oracle only; the native game does not load this reference host.
public final class ClassLoaderReference {
    public static void main(String[] args) throws Exception {
        if (args.length != 0 && args[0].equals("registration")) {
            Method register = ClassLoader.class.getDeclaredMethod("registerNatives");
            Method checkName = ClassLoader.class.getDeclaredMethod("checkName", String.class);
            register.setAccessible(true);
            checkName.setAccessible(true);
            for (int i = 0; i < 256; i++) register.invoke(null);
            if (!Boolean.TRUE.equals(checkName.invoke(null, new Object[]{null})))
                throw new AssertionError("Null class name");
            System.out.println("registration_calls=256;null_name=true");
            return;
        }
        Method getter = Class.class.getDeclaredMethod("getClassLoader0");
        getter.setAccessible(true);
        Class<?>[] types = {int.class, int[][].class, Object.class, String[].class,
                           LoaderIdentity.A.class, LoaderIdentity.B.class,
                           LoaderIdentity.A[][].class};
        for (Class<?> type : types) {
            Object loader = getter.invoke(type);
            if (loader != type.getClassLoader()) throw new AssertionError(type.getName());
            boolean application = loader == LoaderIdentity.class.getClassLoader();
            if (loader != null && !application) throw new AssertionError("Unexpected loader");
            System.out.println(type.getName() + "=" + (application ? "application" : "bootstrap"));
        }
    }
}
