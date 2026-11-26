package dev.boom.reflectforeign;
@SuppressWarnings("deprecation")
public final class ForeignCaller {
    public static Object make(Class<?> target) throws Exception {return target.newInstance();}
}
