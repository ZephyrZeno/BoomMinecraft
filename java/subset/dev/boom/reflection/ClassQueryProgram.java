package dev.boom.reflection;

public final class ClassQueryProgram {
    static Class<?> pick(int n) {
        return switch(n&15) {
            case 0 -> boolean.class; case 1 -> byte.class; case 2 -> char.class;
            case 3 -> short.class; case 4 -> int.class; case 5 -> long.class;
            case 6 -> float.class; case 7 -> double.class; case 8 -> void.class;
            case 9 -> Object.class; case 10 -> String.class; case 11 -> ClassQueryProgram.class;
            case 12 -> Runnable.class; case 13 -> String[][].class;
            case 14 -> int[][][].class; default -> Uninitialized[].class;
        };
    }
    public static int hidden(int n) { return pick(n).isHidden()?1:0; }
    public static int component(int n) {
        Class<?> c=pick(n),part=c.componentType();
        if(part!=c.getComponentType() || c.isArray()!=(part!=null)) return -1;
        return part==null?19:part.getName().hashCode();
    }
    public static int depth(int n) {
        Class<?> c=pick(n); int value=0;
        while(c!=null){value=value*31+c.getName().hashCode();c=c.componentType();}
        return value;
    }
    public static int untouched(int n) {
        Class<?> c=pick(n); c.isHidden(); c.componentType();
        return Initialization.count;
    }
    public static int nullHidden(int n) {
        try {return ((Class<?>)null).isHidden()?1:2;} catch(NullPointerException e){return 73;}
    }
    public static int nullComponent(int n) {
        try {return ((Class<?>)null).componentType()==null?1:2;} catch(NullPointerException e){return 79;}
    }
    public static Class<?> reference(int n) {Class<?> c=pick(n);c.isHidden();return c;}
    public static String descriptor(int n) {return pick(n).descriptorString();}
    public static int nominalLambda(int n) {
        NamedLambda f=()->17; return (f.getClass().isHidden()?100:0)+f.value();
    }
    public interface NamedLambda {int value();}
    static final class Initialization {static int count;}
    static final class Uninitialized {static {Initialization.count+=7;}}
}
