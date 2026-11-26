// Development JVM oracle only; never used as a game execution fallback.
public final class FinalizationPolicyReference {
    public static void main(String[] args) throws Exception {
        var field=Class.forName("java.lang.ref.Finalizer").getDeclaredField("ENABLED");
        field.setAccessible(true);
        System.out.println(field.getBoolean(null));
    }
}
