import java.lang.reflect.Field;
import java.lang.reflect.Method;
public final class ThreadNumberingReference {
    public static void main(String[] args) throws Exception {
        Class<?> c=Class.forName("java.lang.Thread$ThreadNumbering");
        Method next=c.getDeclaredMethod("next");next.setAccessible(true);
        int first=(int)next.invoke(null);
        for(int i=1;i<32;i++)if((int)next.invoke(null)!=first+i)throw new AssertionError("Thread numbering is not sequential");
        Field field=c.getDeclaredField("next");field.setAccessible(true);field.setInt(null,Integer.MAX_VALUE-2);
        int[] values={Integer.MAX_VALUE-2,Integer.MAX_VALUE-1,Integer.MAX_VALUE,Integer.MIN_VALUE,Integer.MIN_VALUE+1};
        for(int expected:values)if((int)next.invoke(null)!=expected)throw new AssertionError("Integer overflow differs");
        System.out.println("sequential_cases=32;overflow_cases=5");
    }
}
