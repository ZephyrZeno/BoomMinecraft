package dev.boom.nativeimage;

import java.lang.invoke.MethodHandles;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.util.ArrayList;
import java.util.List;

/** Exercises the replacement against the unchanged original on a real JVM. */
public final class Log4jServicesProbe {
    public interface Greeting {}
    public static final class First implements Greeting { public First() {} }
    public static final class Second implements Greeting { public Second() {} }

    private static List<String> names(Iterable<?> values) {
        List<String> result = new ArrayList<>();
        for (Object value : values) result.add(value.getClass().getName());
        return result;
    }

    private static void check(Method original, MethodHandles.Lookup lookup,
            Class<?> service, ClassLoader loader, int expected) throws Exception {
        Iterable<?> reference = (Iterable<?>) original.invoke(null, lookup, service, loader, false);
        Iterable<?> adapted = Log4jServices.callServiceLoader(lookup, service, loader, false);
        List<String> a = names(reference);
        List<String> b = names(adapted);
        if (!a.equals(b) || b.size() != expected) {
            throw new AssertionError("Service discovery mismatch: " + a + " / " + b);
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> target = Class.forName("org.apache.logging.log4j.util.ServiceLoaderUtil");
        Method original = target.getDeclaredMethod("callServiceLoader",
                MethodHandles.Lookup.class, Class.class, ClassLoader.class, boolean.class);
        original.setAccessible(true);
        ClassLoader loader = Log4jServicesProbe.class.getClassLoader();
        check(original, MethodHandles.lookup(), Greeting.class, loader, 2);
        check(original, MethodHandles.lookup(), Greeting.class, null, 2);
        check(original, null, Greeting.class, loader, 0);
        check(original, MethodHandles.lookup(), null, loader, 0);
        try (URLClassLoader isolated = new URLClassLoader(new URL[0], null)) {
            check(original, MethodHandles.lookup(), Greeting.class, isolated, 0);
        }
        System.out.println("{\"service_discovery_cases\":5,\"passed\":true}");
    }
}
