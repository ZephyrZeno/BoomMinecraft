import dev.boom.fields.FilterProgram;
import dev.boom.fields.FieldProgram;
public final class FieldFilterReference {
    public static void main(String[] args)throws Exception {
        for(int mode:new int[]{0,3,4,5,1,2,3,4,5,6,7}){
            if(mode==1&&args.length>0){
                java.lang.reflect.Field data=Class.class.getDeclaredField("reflectionData");data.setAccessible(true);
                java.lang.ref.Reference<?> cache=(java.lang.ref.Reference<?>)data.get(FieldProgram.Target.class);
                if(cache==null)throw new AssertionError("Missing reflection data cache");cache.clear();
            }
            System.out.println(Integer.toUnsignedString(FilterProgram.run(mode),16));
        }
    }
}
