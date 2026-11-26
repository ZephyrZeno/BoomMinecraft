import java.lang.reflect.Method;

// Development oracle only; this JVM is not part of the assembly game runtime.
public final class InetAvailabilityReference {
    public static void main(String[] args) throws Exception {
        Class<?> c = Class.forName("java.net.InetAddress");
        Method v4 = c.getDeclaredMethod("isIPv4Available");
        Method v6 = c.getDeclaredMethod("isIPv6Supported");
        v4.setAccessible(true);
        v6.setAccessible(true);
        String before = (Boolean.TRUE.equals(v4.invoke(null)) ? "1" : "0") + " "
            + (Boolean.TRUE.equals(v6.invoke(null)) ? "1" : "0");
        System.setProperty("java.net.preferIPv4Stack", "true".equalsIgnoreCase(System.getProperty("java.net.preferIPv4Stack")) ? "false" : "true");
        String after = (Boolean.TRUE.equals(v4.invoke(null)) ? "1" : "0") + " "
            + (Boolean.TRUE.equals(v6.invoke(null)) ? "1" : "0");
        if (!before.equals(after)) throw new AssertionError("Native availability cache changed");
        System.out.println(before);
    }
}
