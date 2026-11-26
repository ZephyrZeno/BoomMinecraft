package dev.boom.hierarchy;

final class Trace {
    static int bits;
    static int mark(int digit) { bits=bits*10+digit; return digit; }
}
interface I {
    int INIT=Trace.mark(1);
    default int f(int n) { return n+1; }
}
interface J extends I {
    int INIT=Trace.mark(2);
    default int f(int n) { return n+2; }
}
interface K extends I { int f(int n); }
interface Unused { int INIT=Trace.mark(9); }
class Base {
    static int INIT=Trace.mark(3);
    private Object parentRef;
    int value;
    public int f(int n) { return n+4; }
}
class Derived extends Base implements J,Unused {
    static int INIT=Trace.mark(4);
    Object childRef;
    int value;
}
class DefaultI implements I { static int INIT=Trace.mark(5); }
class DefaultJ implements J { static int INIT=Trace.mark(6); }
class OverrideJ implements J { public int f(int n) { return n+7; } }
abstract class AbstractK implements K {}
class Plain {}

public final class Model {
    public static void main(String[] args) throws Exception {
        for(String name:new String[]{"Derived","DefaultI","DefaultJ","OverrideJ","AbstractK"}) {
            Class<?> type=Class.forName("dev.boom.hierarchy."+name,false,Model.class.getClassLoader());
            var method=type.getMethod("f",int.class);
            System.out.println(name+" "+method.getDeclaringClass().getName()+" "+java.lang.reflect.Modifier.isAbstract(method.getModifiers()));
        }
        if(args.length!=0){
            switch(args[0]) {
                case "Derived" -> {new Derived();}
                case "DefaultI" -> {new DefaultI();}
                case "DefaultJ" -> {new DefaultJ();}
            }
            System.out.println("TRACE "+Trace.bits);
        }
    }
}
