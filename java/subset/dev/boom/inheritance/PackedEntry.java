package dev.boom.inheritance;

class Dense extends Base {
    boolean f0, f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11, f12, f13, f14, f15, f16, f17, f18, f19, f20, f21, f22, f23, f24, f25, f26, f27, f28, f29, f30, f31;
    byte left,right;
    short small;
    char character;
    int count;
    float factor;
    long total;
    double fraction;
    private Token extra;
    Dense(int n){
        super(n+1);
        f0=((n>>>0)&1)!=0;
        f1=((n>>>1)&1)!=0;
        f2=((n>>>2)&1)!=0;
        f3=((n>>>3)&1)!=0;
        f4=((n>>>4)&1)!=0;
        f5=((n>>>5)&1)!=0;
        f6=((n>>>6)&1)!=0;
        f7=((n>>>7)&1)!=0;
        f8=((n>>>8)&1)!=0;
        f9=((n>>>9)&1)!=0;
        f10=((n>>>10)&1)!=0;
        f11=((n>>>11)&1)!=0;
        f12=((n>>>12)&1)!=0;
        f13=((n>>>13)&1)!=0;
        f14=((n>>>14)&1)!=0;
        f15=((n>>>15)&1)!=0;
        f16=((n>>>16)&1)!=0;
        f17=((n>>>17)&1)!=0;
        f18=((n>>>18)&1)!=0;
        f19=((n>>>19)&1)!=0;
        f20=((n>>>20)&1)!=0;
        f21=((n>>>21)&1)!=0;
        f22=((n>>>22)&1)!=0;
        f23=((n>>>23)&1)!=0;
        f24=((n>>>24)&1)!=0;
        f25=((n>>>25)&1)!=0;
        f26=((n>>>26)&1)!=0;
        f27=((n>>>27)&1)!=0;
        f28=((n>>>28)&1)!=0;
        f29=((n>>>29)&1)!=0;
        f30=((n>>>30)&1)!=0;
        f31=((n>>>31)&1)!=0;
        left=(byte)(n^0x5a);right=(byte)(n^0xa5);small=(short)n;character=(char)n;
        count=n*37;factor=n*0.25f;total=((long)n)*9876543211L;fraction=n*0.125;extra=new Token(n+42);
    }
    int flags(){return (f0?1:0)+(f1?1:0)+(f2?1:0)+(f3?1:0)+(f4?1:0)+(f5?1:0)+(f6?1:0)+(f7?1:0)+(f8?1:0)+(f9?1:0)+(f10?1:0)+(f11?1:0)+(f12?1:0)+(f13?1:0)+(f14?1:0)+(f15?1:0)+(f16?1:0)+(f17?1:0)+(f18?1:0)+(f19?1:0)+(f20?1:0)+(f21?1:0)+(f22?1:0)+(f23?1:0)+(f24?1:0)+(f25?1:0)+(f26?1:0)+(f27?1:0)+(f28?1:0)+(f29?1:0)+(f30?1:0)+(f31?1:0);}
    int summary(){return fields()+flags()+left*3+right*5+small*7+character*11+count+extra.value;}
}
class DenseState {static Dense ROOT=new Dense(-1);}
public final class PackedEntry {
    public static int narrow(int n){return new Dense(n).summary();}
    public static int adjacent(int n){Dense value=new Dense(n);value.left=(byte)n;value.right=(byte)(n>>>8);return value.summary();}
    public static int floatNeighbor(int n,float f){Dense value=new Dense(n);value.factor=f;return (int)value.factor+value.summary();}
    public static float floatValue(int n,float f){Dense value=new Dense(n);value.factor=f;return value.factor;}
    public static long longValue(int n,long extra){Dense value=new Dense(n);value.total=extra;return value.total+value.wide+value.summary();}
    public static double doubleValue(int n,double extra){Dense value=new Dense(n);value.fraction=extra;return value.fraction+value.decimal+value.summary();}
    public static Dense make(int n){return new Dense(n);}
    public static int writeByte(int which,int n){if(which==0)DenseState.ROOT.left=(byte)n;else DenseState.ROOT.right=(byte)n;return 1;}
}
