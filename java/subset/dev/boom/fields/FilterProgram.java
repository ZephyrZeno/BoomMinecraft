package dev.boom.fields;
import java.lang.reflect.Field;
import java.util.Set;
import jdk.internal.reflect.Reflection;
public final class FilterProgram {
    static Field saved;
    static void hide(){Reflection.registerFieldsToFilter(FieldProgram.Target.class,Set.of("number","wide"));}
    public static int run(int mode){
        try {
            if(mode==0){saved=FieldProgram.Target.class.getDeclaredField("number");return saved.getName().hashCode();}
            if(mode==1){hide();return FieldProgram.initialized;}
            if(mode==2)return saved.getName().hashCode();
            if(mode==3)return FieldProgram.Target.class.getDeclaredField("number").getName().hashCode();
            if(mode==4)return FieldProgram.Target.class.getDeclaredField("wide").getName().hashCode();
            if(mode==5)return FieldProgram.Target.class.getDeclaredField("text").getName().hashCode();
            if(mode==6){hide();return 0;}
            return FieldProgram.initialized;
        }catch(NoSuchFieldException e){return 0x71000000^e.getMessage().hashCode();}
        catch(IllegalArgumentException e){return 0x72000000;}
    }
}
