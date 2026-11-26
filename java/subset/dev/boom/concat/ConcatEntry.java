package dev.boom.concat;
public final class ConcatEntry {
    static String text(int which) {
        switch (which & 7) {
            case 0: return null;
            case 1: return "";
            case 2: return "hello";
            case 3: return "A\u0000B";
            case 4: return "世界🚀";
            case 5: return "\ud800x\udfff";
            case 6: return "Aa";
            default: return "BB";
        }
    }
    static String intText(int value) { return "I:"+value+"!"; }
    static String longText(long value) { return "J:"+value+"!"; }
    public static int intHash(int value) { return intText(value).hashCode(); }
    public static int longHash(long value) { return longText(value).hashCode(); }
    public static int character(int value, int index) { return intText(value).charAt(index); }
    public static int longCharacter(long value, int index) { return longText(value).charAt(index); }
    public static int longLength(long value) { return longText(value).length(); }
    public static int classNameConcat(int value) { return (java.io.File.class.getName()+":"+value).hashCode(); }
    public static int mixed(int value, long wide, int flag, int unit, int which) {
        return ("["+value+":"+wide+":"+(flag!=0)+":"+(char)unit+":"+text(which)+"]").hashCode();
    }
    public static int controlConstants(int value) { return ("\u0001\u0002\u0000\ud800="+value+"\u0002").hashCode(); }
    public static int nested(int value, long wide) { return (intText(value)+"/"+longText(wide)).hashCode(); }
    public static int independent(int value) { return intText(value)==intText(value) ? 1 : 0; }
    public static int interned(int value) { return intText(value).intern()==intText(value).intern() ? 1 : 0; }
    public static int internBeforeLiteral(int ignored) {
        String value=intText(7);
        String canonical=value.intern();
        return canonical=="I:7!" ? 1 : 0;
    }
    public static int literalBeforeIntern(int ignored) {
        String literal="I:7!";
        return (intText(7).intern()==literal ? 1 : 0) | (intText(7)==literal ? 2 : 0);
    }
    public static int collisions(int value) {
        String a=""+text(6)+value;
        String b=""+text(7)+value;
        return (a.hashCode()==b.hashCode() ? 1 : 0) | (a.intern()==b.intern() ? 2 : 0) | (a.equals(b) ? 4 : 0);
    }
    public static int arrays(int count, int index, int value) {
        String[] strings=new String[count];strings[index]=intText(value);
        return strings[index].hashCode() ^ strings.length;
    }
    public static int state(int value) {
        ConcatState.value=intText(value);
        ConcatState.interned=ConcatState.value.intern();
        return ConcatState.interned.hashCode();
    }
    public static int rejectedFloat(float value) { return ("F:"+value).length(); }
    public static int rejectedObject(Object value) { return ("O:"+value).length(); }
    public static int rejectedLambda(int value) { Runnable task=()->{};task.run();return value; }
}
