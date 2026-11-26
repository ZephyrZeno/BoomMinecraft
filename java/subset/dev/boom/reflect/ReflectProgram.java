package dev.boom.reflect;
@SuppressWarnings("deprecation")
public final class ReflectProgram {
    public static int initCount;
    public static class Value {
        public static int initialized;
        static { initCount++;initialized=9; }
        public int value;
        public Value(){value=initialized+33;}
    }
    public static class PrivateValue { public int value;private PrivateValue(){value=77;} }
    public static class NoDefault { public NoDefault(int x){} }
    public abstract static class AbstractValue { public AbstractValue(){} }
    public interface InterfaceValue {}
    public static class Marker extends RuntimeException { public Marker(){} }
    public static class Throws {
        public static final Marker MARKER=new Marker();
        public Throws(){throw MARKER;}
    }
    public static class BadInit {
        static { if(fail())throw new Marker(); }
        private static boolean fail(){return true;}
        public BadInit(){}
    }
    public static Class<?> target(int kind) {
        return switch(kind){
            case 0 -> Value.class;case 1 -> PrivateValue.class;
            case 2 -> NoDefault.class;case 3 -> AbstractValue.class;
            case 4 -> InterfaceValue.class;case 5 -> int[].class;
            case 6 -> Class.class;case 7 -> Object.class;
            case 8 -> PackageValue.class;case 9 -> Throws.class;
            case 10 -> BadInit.class;default -> null;
        };
    }
    public static Object run(int kind,int route,int operation) throws Exception {
        Class<?> target=target(kind);
        if(operation==0)return target;
        if(route==1)return OtherCaller.make(target);
        if(route==2)return dev.boom.reflectforeign.ForeignCaller.make(target);
        return target.newInstance();
    }
}
class PackageValue {public int value;PackageValue(){value=61;}}
