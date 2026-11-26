import java.lang.reflect.*;
import jdk.internal.misc.Unsafe;
public final class ClassValueFieldReference {
    public static void main(String[] args) throws Exception {
        Unsafe u=Unsafe.getUnsafe();long offset=u.objectFieldOffset(Class.class,"classValueMap");
        Method read=ClassValue.class.getDeclaredMethod("getCacheCarefully",Class.class);read.setAccessible(true);
        Constructor<?> create=Class.forName("java.lang.ClassValue$ClassValueMap").getDeclaredConstructor();create.setAccessible(true);
        for(Class<?> type:new Class<?>[]{Object.class,String.class,int.class,byte.class,Object[].class}) {
            Object prior=u.getReference(type,offset);
            try {
                u.putReference(type,offset,null);Object[] empty=(Object[])read.invoke(null,type);boolean stableEmpty=empty==read.invoke(null,type);
                u.putReference(type,offset,create.newInstance());Object[] populated=(Object[])read.invoke(null,type);boolean stable=populated==read.invoke(null,type);
                u.putReference(type,offset,null);System.out.println(empty.length+"|"+stableEmpty+"|"+populated.length+"|"+stable+"|"+(empty!=populated)+"|"+(empty==read.invoke(null,type)));
            } finally {u.putReference(type,offset,prior);}
        }
        try{read.invoke(null,(Object)null);throw new AssertionError("null Class accepted");}
        catch(InvocationTargetException error){System.out.println(error.getCause() instanceof NullPointerException?"npe":"wrong error");}
    }
}
