package dev.boom.fields;

public final class ClassNamesProgram {
    static int initialized;
    static class Cold { static { initialized++; } }
    static class Member { class Nested$Name {} }
    interface Marker {}
    enum Choice { A }
    public static String run(int mode) {
        class Local { class Child {} }
        if(mode >= 63) return switch(mode) {
            case 63 -> identity(Object[].class,"java.lang.Object[]",false);
            case 64 -> identity(Member.class,"dev.boom.fields.ClassNamesProgram.Member",false);
            case 65 -> identity(Object.class,"java.lang.Object",false);
            case 66 -> identity(int.class,"int",false);
            case 67 -> identity(String.class,"String",true);
            case 68 -> identity(Member.class,"Member",true);
            case 69 -> identity(Local.class,"Local",true);
            case 70 -> identity(int.class,"int",true);
            case 71 -> identity(new Object(){}.getClass(),"",true);
            default -> identity(Names$Top.class,"Names$Top",true);
        };
        Class<?> type = switch (mode / 3) {
            case 0 -> Object.class;
            case 1 -> String.class;
            case 2 -> int.class;
            case 3 -> void.class;
            case 4 -> byte[][].class;
            case 5 -> String[][][].class;
            case 6 -> ClassNamesProgram.class;
            case 7 -> Member.class;
            case 8 -> Member.Nested$Name.class;
            case 9 -> Member.Nested$Name[][].class;
            case 10 -> Marker.class;
            case 11 -> Choice.class;
            case 12 -> Local.class;
            case 13 -> Local[].class;
            case 14 -> Local.Child.class;
            case 15 -> Local.Child[][].class;
            case 16 -> new Object() {}.getClass();
            case 17 -> Names$Top.class;
            case 18 -> Names$Top.class;
            case 19 -> Cold.class;
            default -> null;
        };
        try {
            String name = switch (mode % 3) {
                case 0 -> type.getName();
                case 1 -> type.getCanonicalName();
                default -> type.getSimpleName();
            };
            return name + ":" + initialized;
        } catch (NullPointerException error) { return "npe"; }
    }
    private static String identity(Class<?> type,String literal,boolean simple) {
        String a=simple?type.getSimpleName():type.getCanonicalName();
        String b=simple?type.getSimpleName():type.getCanonicalName();
        return (a==b)+":"+(a==literal)+":"+(a==type.getName())+":"+initialized;
    }
}
class Names$Top {}
