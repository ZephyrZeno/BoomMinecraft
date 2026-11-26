import java.lang.reflect.*;
public final class BootstrapLookupReference {
    public static final String[] CASES={"java.lang.Object","java.lang.String","java.lang.Class","java.lang.Throwable","java.lang.ClassLoader","dev.boom.MissingBootstrap","","[I","[Ljava.lang.String;","java/lang/String","java.sql.Driver","int",null,"java.lang.Str\0ing","java.lang.Ｓtring"};
    public static void main(String[] args) throws Exception {
        Method m=ClassLoader.class.getDeclaredMethod("findBootstrapClassOrNull",String.class);m.setAccessible(true);
        for(String name:CASES) {
            try { Class<?> type=(Class<?>)m.invoke(null,name);System.out.println(type==null?"null":type.getName()); }
            catch(InvocationTargetException error){System.out.println("error:"+error.getCause().getClass().getName());}
        }
    }
}
