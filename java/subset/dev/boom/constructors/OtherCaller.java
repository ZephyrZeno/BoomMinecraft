package dev.boom.constructors;
import java.lang.reflect.Constructor;
public final class OtherCaller {public static Object invoke(Constructor<?> constructor,Object[] args)throws Exception{return constructor.newInstance(args);}}
