import java.lang.reflect.Method;
public final class ShutdownHaltReference {
    public static void main(String[] args) throws Exception {
        Method halt=Class.forName("java.lang.Shutdown").getDeclaredMethod("halt",int.class);halt.setAccessible(true);halt.invoke(null,Integer.parseInt(args[0]));
        throw new AssertionError("Shutdown.halt returned");
    }
}
