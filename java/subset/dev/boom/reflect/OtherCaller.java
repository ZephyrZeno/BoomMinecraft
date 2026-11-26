package dev.boom.reflect;
@SuppressWarnings("deprecation")
public final class OtherCaller {
    public static Object make(Class<?> target) throws Exception {return target.newInstance();}
}
