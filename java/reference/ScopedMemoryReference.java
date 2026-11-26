// Locked JVM oracle only; the delivered native runtime never invokes this host.
public final class ScopedMemoryReference {
    public static void main(String[] args) throws Exception {
        Class<?> type=Class.forName("jdk.internal.misc.ScopedMemoryAccess");
        var get=type.getDeclaredMethod("getScopedMemoryAccess");
        var register=type.getDeclaredMethod("registerNatives");
        get.setAccessible(true);register.setAccessible(true);
        Object first=get.invoke(null);
        for(int i=0;i<256;i++)register.invoke(null);
        for(int i=0;i<4096;i++)if(get.invoke(null)!=first)throw new AssertionError("Singleton identity");
        if(first==null||first.getClass()!=type||type.getClassLoader()!=null)throw new AssertionError("Bootstrap instance");
        System.out.println("singleton_identity=1;bootstrap=1;register_calls=256");
    }
}
