import dev.boom.reflection.ArrayReflection;
import java.lang.reflect.Array;
import java.util.Arrays;

// Locked JVM oracle only. Lines are fixed test data, never game inputs.
public final class ArrayReflectionReference {
    static String descriptor(Class<?> c) { return c == null ? "null" : c.descriptorString(); }
    static long[] measure(Object value) {
        Class<?> component=value.getClass().getComponentType();
        int n=Array.getLength(value);
        int size=!component.isPrimitive()?8:component==boolean.class||component==byte.class?1:component==char.class||component==short.class?2:component==int.class||component==float.class?4:8;
        long arrays=1,bytes=(long)n*size;
        if(!component.isPrimitive()) for(int i=0;i<n;i++) {
            Object child=Array.get(value,i);
            if(child!=null) { long[] m=measure(child); arrays+=m[0];bytes+=m[1]; }
        }
        return new long[]{arrays,bytes};
    }
    static void sample(Class<?> type, int operation, int[] counts) {
        Object result=ArrayReflection.allocate(type,operation==0?counts[0]:0,counts,operation==0?0:operation==1?3:operation+2);
        int kind=result instanceof NullPointerException?4:result instanceof NegativeArraySizeException?2:result instanceof IllegalArgumentException?18:result instanceof ClassCastException?12:0;
        long[] m=kind==0&&operation<2?measure(result):new long[2];
        String encoded=counts==null?"null":String.join(",",Arrays.stream(counts).mapToObj(Integer::toString).toList());
        System.out.println(descriptor(type)+"|"+operation+"|"+encoded+"|"+kind+"|"+descriptor(kind==0&&operation>=2?(Class<?>)result:result.getClass())+"|"+m[0]+"|"+m[1]);
    }
    public static void main(String[] args) throws Exception {
        Class<?>[] types={null,void.class,boolean.class,byte.class,char.class,short.class,int.class,long.class,float.class,double.class,Object.class,String.class,ArrayReflection.Element.class,int[].class,ArrayReflection.Element[][].class,Class.forName("[".repeat(254)+"I"),Class.forName("[".repeat(255)+"I"),Runnable.class,ArrayReflection.Marker.class};
        for(Class<?> type:types) {
            for(int n:new int[]{Integer.MIN_VALUE,-3,-1,0,1,4,17,127})sample(type,0,new int[]{n});
            for(int[] dims:new int[][]{null,{}, {-1},{0},{1},{2,3},{0,-1},{1,0},{Integer.MIN_VALUE,0}})sample(type,1,dims);
            for(int operation=2;operation<5;operation++)sample(type,operation,null);
        }
        for(int[] dims:new int[][]{new int[255],new int[256],{1,2,3},{0,0,0},{1,-1,2}})sample(int.class,1,dims);
        int[] deep=new int[254];Arrays.fill(deep,1);sample(int.class,1,deep);
        if(ArrayReflection.initialized!=0)throw new AssertionError("Array allocation initialized its component class");
    }
}
