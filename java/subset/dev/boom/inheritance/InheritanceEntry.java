package dev.boom.inheritance;

final class Trace {static int bits;static int mark(int n){bits=bits*10+n;return n;}}
final class Token {int value;Token(int n){value=n;}}
interface Default {int INIT=Trace.mark(6);default int bonus(int n){return n+6;}}
class Base {
    static int INIT=Trace.mark(1);
    static int SHARED=17;
    int value;
    private Token token;
    long wide;
    double decimal;
    final int fixed;
    int during;
    Base(int n){value=n;token=new Token(n+9);wide=((long)n)*12345678901L;decimal=n*0.5;fixed=n+3;during=f(n);}
    public int f(int n){return value+n;}
    public int fields(){return value+token.value+fixed+during;}
    public long wide(long n){return wide+n;}
    public double decimal(double n){return decimal+n;}
    static int staticPlus(int n){return n+SHARED;}
}
class Child extends Base implements Default {
    static int INIT=Trace.mark(2);
    int value;
    private Token token;
    Child(int n){super(n+1);value=n*2;token=new Token(n+5);}
    public int f(int n){return value*3+n;}
    public int childFields(){return value+token.value;}
    public int superCall(int n){return super.f(n)+Default.super.bonus(n);}
}
class Grand extends Child {
    static int INIT=Trace.mark(3);
    Token extra;
    short narrow;
    Grand(int n){this(n,7);}
    Grand(int n,int k){super(n);extra=new Token(n+k);narrow=(short)n;}
    public int grandFields(){return extra.value+narrow;}
    public int f(int n){return value*5+n;}
    public int superCall(int n){return super.superCall(n)+super.f(n);}
}
class State {static Base ROOT=new Grand(7);}
class FailBase {int value;FailBase(int n){value=1/n;}}
class FailChild extends FailBase {Token ref;FailChild(int n){super(n);ref=new Token(n);}}
public final class InheritanceEntry {
    static Base pick(int kind,int n){switch(kind&3){case 0:return new Base(n);case 1:return new Child(n);default:return new Grand(n);}}
    public static int fields(int kind,int n){Base value=pick(kind,n);return value.fields()+value.f(n);}
    public static int hidden(int n){Child value=new Child(n);return value.value+((Base)value).value*13+value.childFields();}
    public static int constructed(int n){Grand value=new Grand(n);return value.fields()+value.childFields()+value.grandFields();}
    public static long wide(int kind,int n,long extra){return pick(kind,n).wide(extra);}
    public static double decimal(int kind,int n,double extra){return pick(kind,n).decimal(extra);}
    public static int casts(int kind,int n){Base value=pick(kind,n);if(value instanceof Grand)return ((Grand)value).grandFields();return value.fields();}
    public static int initialization(int n){Base value=new Grand(n);return value.f(n)+Trace.bits*100;}
    public static int inheritedStatic(int n){return Child.SHARED+Child.staticPlus(n)+Trace.bits*1000;}
    public static int inheritedDefault(int n){Default value=new Grand(n);return value.bonus(n);}
    public static int special(int kind,int n){Base value=pick(kind,n);if(value instanceof Grand)return ((Grand)value).superCall(n);if(value instanceof Child)return ((Child)value).superCall(n);return value.f(n);}
    public static int array(int n){Base[] values=new Child[2];values[0]=new Grand(n);return values[0].fields()+values[0].f(n)+values.length;}
    public static int arrayFault(int kind,int n,int index){Base[] values=kind==0?null:kind==1?new Grand[2]:new Child[2];values[index]=new Base(n);return values.length;}
    public static int nullArrayStore(int index){Child[] actual=new Child[2];Base[] values=actual;values[index]=null;return values.length+(values[0]==null?1:0);}
    public static int interfaceArray(int n){Default[] values=new Default[2];values[0]=new Grand(n);Default[] alias=new Child[2];alias[0]=new Grand(n+1);return values[0].bonus(n)+alias[0].bonus(n)+values.length+alias.length;}
    public static int retained(int n){Base value=State.ROOT;return value.fields()+((Grand)value).childFields()+((Grand)value).grandFields()+n;}
    public static int constructorFailure(int n){FailChild value=new FailChild(n);return value.value+value.ref.value;}
}
