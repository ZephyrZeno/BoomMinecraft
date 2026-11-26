import java.lang.reflect.*;
public final class ClassBootstrapReference {
    public static void main(String[] args) throws Exception {
        Class<?>[] types={boolean.class,byte.class,char.class,short.class,int.class,long.class,float.class,double.class,void.class};
        Method primitive=Class.class.getDeclaredMethod("getPrimitiveClass",String.class);
        primitive.setAccessible(true);
        for(Class<?> t:types){
            if(primitive.invoke(null,t.getName())!=t)throw new AssertionError("Primitive identity changed");
            System.out.println(t.getName()+"\t"+t.isPrimitive()+"\t"+t.desiredAssertionStatus());
        }
        for(String n:new String[]{"EMPTY_CLASS_ARRAY","serialPersistentFields"}){
            Field f=Class.class.getDeclaredField(n);f.setAccessible(true);
            System.out.println(n+"\t"+Array.getLength(f.get(null)));
        }
        for(String n:new String[]{"","Integer","java.lang.Integer","INT","int\0","中文","\ud800"}){
            try {primitive.invoke(null,n);throw new AssertionError("Unknown primitive accepted");}
            catch(InvocationTargetException e){if(!(e.getCause() instanceof ClassNotFoundException))throw e;}
        }
        System.out.println("invalid_names\t7\tClassNotFoundException");
    }
}
