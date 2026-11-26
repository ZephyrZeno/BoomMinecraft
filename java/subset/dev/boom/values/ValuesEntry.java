package dev.boom.values;

public final class ValuesEntry {
    public static int character(int n) {
        String s=String.valueOf((char)n);
        return s.hashCode()*31+s.length()*7+s.charAt(0);
    }
    public static int integer(int n) {String s=String.valueOf(n);return s.hashCode()*31+s.length();}
    public static int wide(long n) {String s=String.valueOf(n);return s.hashCode()*31+s.length();}
    public static int integerDirect(int n) {String s=Integer.toString(n);return s.hashCode()*31+s.length();}
    public static int wideDirect(long n) {String s=Long.toString(n);return s.hashCode()*31+s.length();}
    public static int freshDirect(int n) {
        String a=Integer.toString(n),b=Integer.toString(n),p=Long.toString(n),q=Long.toString(n);
        return (a==b?1:0)|(p==q?2:0)|(a.equals(b)?4:0)|(p.equals(q)?8:0);
    }
    public static int bool(int n) {
        boolean flag=(n&1)!=0;
        String s=String.valueOf(flag);
        return s.hashCode()+(s==(flag?"true":"false")?1:0)+(s.intern()==s?2:0);
    }
    public static int fresh(int n) {
        String a=String.valueOf((char)n),b=String.valueOf((char)n);
        String i=String.valueOf(n),j=String.valueOf(n);
        String p=String.valueOf((long)n),q=String.valueOf((long)n);
        return (a==b?1:0)|(i==j?2:0)|(p==q?4:0)|(a.equals(b)?8:0)|(i.equals(j)?16:0)|(p.equals(q)?32:0);
    }
    public static int combined(int n) {
        return String.join("/",String.valueOf((char)n),String.valueOf(n),String.valueOf((long)n),String.valueOf((n&1)!=0)).hashCode();
    }
    public static int parallel(int n) {return String.valueOf((char)n).hashCode();}
    public static int unsupported(float n) {return String.valueOf(n).hashCode();}
    public static int unsupportedRadix(int n) {return Integer.toString(n,16).hashCode();}
}
