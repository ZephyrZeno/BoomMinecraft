package dev.boom.dispatch;

final class Trace {
    static int bits;
    static int mark(int digit) { bits=bits*10+digit;return digit; }
}
interface Root {
    int INIT=Trace.mark(1);
    default int f(int n) {return n+1;}
    private int twice(int n) {return n*2;}
    default int nested(int n) {return twice(f(n));}
    default long wide(long n,double d) {return n+(long)d;}
    default String identity(String s) {return s;}
}
interface Child extends Root {
    int INIT=Trace.mark(2);
    default int f(int n) {return n+2;}
}
interface Reabstract extends Root {int f(int n);}
interface Marker {int INIT=Trace.mark(9);}
class A implements Root {
    int value;
    A(int value){this.value=value;}
    public int f(int n){return n+value;}
}
class B implements Child {static int INIT=Trace.mark(3);}
class C implements Reabstract {public int f(int n){return n*3;}}
class D implements Child,Marker {static int INIT=Trace.mark(4);}
abstract class Pending implements Reabstract {}
abstract class Gap implements Reabstract {}
class Plain {}

public final class DispatchEntry {
    static Root pick(int kind,int n) {
        switch(kind&3){case 0:return new A(n);case 1:return new B();case 2:return new C();default:return new D();}
    }
    public static int choose(int kind,int n){return pick(kind,n).f(n);}
    public static int nested(int kind,int n){return pick(kind,n).nested(n);}
    public static long wide(int kind,long n,double d){return pick(kind,7).wide(n,d);}
    public static int reference(int kind,int n){return pick(kind,n).identity("assembly").length()+n;}
    public static int nil(int n){Root value=null;return value.f(n);}
    public static int initialization(int n){Root value=new D();return value.f(n)+Trace.bits*100;}
    public static int direct(int n){return new B().f(n);}
    public static int read(Root value,int n){if(n==17)new Plain();return value.f(n);}
    public static int external(int n){dev.boom.dispatch.api.PublicContract value=new dev.boom.dispatch.api.PublicBox();return value.f(n);}
}
