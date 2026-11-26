package dev.boom.fields;
import java.lang.reflect.*;

public final class FieldProgram {
    static int initialized;
    public static class Parent { public static int inherited; }
    public static final class Target extends Parent {
        private static volatile int number=17;
        static long wide=0x123456789abcdef0L;
        static String reference;
        final String text=null;
        private String[] names;
        byte small;
        static { initialized++; }
    }
    enum Tiny { A }
    public static Field raw(int which)throws NoSuchFieldException {
        if(which==9999)initialized=Target.number;
        return field(which);
    }
    static Field field(int which)throws NoSuchFieldException {
        return switch(which) {
            case 0->Target.class.getDeclaredField("number");
            case 1->Target.class.getDeclaredField("wide");
            case 2->Target.class.getDeclaredField("text");
            case 3->Target.class.getDeclaredField("names");
            case 4->Target.class.getDeclaredField("small");
            case 5->Tiny.class.getDeclaredField("A");
            case 6->Class.class.getDeclaredField("name");
            case 7->Class.class.getDeclaredField("classLoader");
            case 8->Class.class.getDeclaredField("classData");
            case 9->ClassLoader.class.getDeclaredField("name");
            case 10->Field.class.getDeclaredField("name");
            case 11->Constructor.class.getDeclaredField("clazz");
            case 12->Method.class.getDeclaredField("name");
            case 13->Module.class.getDeclaredField("name");
            case 14->AccessibleObject.class.getDeclaredField("override");
            case 15->System.class.getDeclaredField("security");
            case 16->Target.class.getDeclaredField("inherited");
            case 17->Target.class.getDeclaredField("absent\u0000\ud800");
            case 18->int.class.getDeclaredField("number");
            case 19->Target[].class.getDeclaredField("length");
            case 20->Target.class.getDeclaredField(null);
            default->((Class<?>)null).getDeclaredField("number");
        };
    }
    public static long run(int mode,int which) {
        try {
            if(mode==10)return Target.number;
            if(mode==11)return initialized;
            Field f=field(which);
            return switch(mode) {
                case 0->initialized;
                case 1->((long)f.getName().hashCode()<<32)^(f.getType().getName().hashCode()&0xffffffffL);
                case 2->((long)f.getModifiers()<<32)^(f.getDeclaringClass().getName().hashCode()&0xffffffffL);
                case 3->((long)f.hashCode()<<32)^(f.isSynthetic()?1:0)^(f.isEnumConstant()?2:0);
                case 4->{Field second=field(which);yield(f==second?1:0)|(f.equals(second)?2:0)|(f.hashCode()==second.hashCode()?4:0)|(f.equals(null)?8:0)|(f.equals(new Object())?16:0);}
                default->f.equals(field((which+1)%5))?1:0;
            };
        } catch(NoSuchFieldException e) {
            return 0x7100000000000000L^(e.getMessage().hashCode()&0xffffffffL);
        } catch(NullPointerException e) {
            return 0x7200000000000000L;
        }
    }
}
