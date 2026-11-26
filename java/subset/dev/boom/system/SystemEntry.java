package dev.boom.system;

public final class SystemEntry {
    static Object source;
    static Object destination;
    static Object make(int kind, boolean dest) {
        return switch (kind) {
            case 0 -> new boolean[]{true,false,true,true,false,false,true,false};
            case 1 -> new byte[]{-128,127,1,-3,0,16,64,-1};
            case 2 -> new char[]{0,65535,55296,1024,1,32,1000,2000};
            case 3 -> new short[]{-32768,32767,1,-3,0,16,2000,-1};
            case 4 -> new int[]{0x80000000,0x7fffffff,1,-3,0,16,2000,-1};
            case 5 -> new long[]{0x8000000000000000L,0x7fffffffffffffffL,1,-3,0,16,2000,-1};
            case 6 -> new float[]{Float.NaN,-0.0f,1.25f,-3,0,16,2000,-1};
            case 7 -> new double[]{Double.NaN,-0.0,1.25,-3,0,16,2000,-1};
            case 8 -> new String[]{"a",null,"b","c","d","e","f","g"};
            case 9 -> new Base[]{new Child(1),null,new Base(3),new Child(4),null,new Child(6),new Base(7),null};
            case 10 -> dest ? new Base[8] : new Child[]{new Child(1),null,new Child(3),new Child(4),null,new Child(6),new Child(7),null};
            case 11 -> dest ? new String[]{"old","old","old","old","old","old","old","old"} : new Object[]{"a",null,"b",new Base(4),"c",null,"d","e"};
            case 12 -> dest ? new String[8] : new Object[8];
            case 13 -> dest ? new byte[8] : new boolean[8];
            case 14 -> dest ? new long[8] : new int[8];
            case 15 -> dest ? new Object[8] : new int[8];
            case 16 -> dest ? new Object() : new int[8];
            case 17 -> dest ? new int[8] : new Object();
            case 18 -> dest ? new int[8] : null;
            case 19 -> dest ? null : new int[8];
            case 20 -> dest ? null : new Object();
            default -> null;
        };
    }
    static int hash(Object a) {
        int h=1;
        if (a instanceof boolean[] v) {for(int i=0;i<v.length;i++) h=h*31+(v[i]?1:0);}
        else if (a instanceof byte[] v) {for(int i=0;i<v.length;i++) h=h*31+v[i];}
        else if (a instanceof char[] v) {for(int i=0;i<v.length;i++) h=h*31+v[i];}
        else if (a instanceof short[] v) {for(int i=0;i<v.length;i++) h=h*31+v[i];}
        else if (a instanceof int[] v) {for(int i=0;i<v.length;i++) h=h*31+v[i];}
        else if (a instanceof long[] v) {for(int i=0;i<v.length;i++) h=h*31+(int)(v[i]^(v[i]>>>32));}
        else if (a instanceof float[] v) {for(int i=0;i<v.length;i++) h=h*31+(int)v[i];}
        else if (a instanceof double[] v) {for(int i=0;i<v.length;i++) h=h*31+(int)v[i];}
        else if (a instanceof Object[] v) {for(int i=0;i<v.length;i++){Object x=v[i]; h=h*31+(x==null?0:x instanceof String s?s.hashCode():((Base)x).value);}}
        return h;
    }
    public static int copy(int kind,int from,int to,int count) {
        if(kind==-1) return hash(source)*17+hash(destination);
        int k=kind&31;
        source=make(k,false);
        destination=(kind&32)!=0?source:make(k,true);
        System.arraycopy(source,from,destination,to,count);
        return hash(source)*17+hash(destination);
    }
    public static int parallel(int n) {
        int[] a={n,n+1,n+2,n+3,n+4,n+5,n+6,n+7};
        System.arraycopy(a,0,a,2,6);
        return a[0]+a[2]*3+a[7]*7;
    }
    @SuppressWarnings("removal")
    public static int registration(int n) {
        if(System.getSecurityManager()!=null) return -1;
        long before=System.nanoTime();
        int result=parallel(n);
        return (System.currentTimeMillis()>0 && System.nanoTime()-before>=0) ? result : -2;
    }
    public static int unsupportedPhase(int ignored) { return System.getProperty("java.version").length(); }
}
class Base { int value; Base(int n){value=n;} }
final class Child extends Base { Child(int n){super(n);} }
