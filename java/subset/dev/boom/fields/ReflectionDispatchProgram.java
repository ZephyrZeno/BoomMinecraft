package dev.boom.fields;
import java.lang.reflect.*;

public final class ReflectionDispatchProgram {
    static final class Target {
        int value;
        private volatile long counter;
        public static final String[][] texts = null;
        transient java.util.List<String> list;
        public Target() {}
        private Target(int value) { this.value = value; }
        protected Target(String[] text, int[][] values) throws java.io.IOException, IllegalArgumentException {}
        Target(long value, byte... bytes) {}
    }
    public static String run(int mode) throws Exception {
        Constructor<?> first = Target.class.getDeclaredConstructor();
        Field field = Target.class.getDeclaredField("value");
        if (mode == 0) return first.toString();
        if (mode == 1) return field.toString();
        if (mode == 2) return Target.class.getDeclaredConstructor(int.class).toString();
        if (mode == 3) return Target.class.getDeclaredConstructor(String[].class, int[][].class).toString();
        if (mode == 4) return Target.class.getDeclaredConstructor(long.class, byte[].class).toString();
        if (mode == 5) return Target.class.getDeclaredField("counter").toString();
        if (mode == 6) return Target.class.getDeclaredField("texts").toString();
        if (mode == 7) return Target.class.getDeclaredField("list").toString();
        if (mode == 8) {
            Object a = first, b = field;
            if (!a.equals(Target.class.getDeclaredConstructor()) || !b.equals(Target.class.getDeclaredField("value"))) return "equals-failed";
            if (a.equals(b) || b.equals(a) || a.equals(null) || b.equals(null)) return "cross-equals-failed";
            if (a.hashCode() != first.hashCode() || b.hashCode() != field.hashCode()) return "hash-failed";
            if (first.toString() == first.toString() || field.toString() == field.toString()) return "fresh-identity-failed";
            return "ok";
        }
        if (mode == 9 || mode == 10) {
            Member member = mode == 9 ? first : field;
            if (member.getDeclaringClass() != Target.class || member.isSynthetic()) return "member-failed";
            if (member.getModifiers() != (mode == 9 ? 1 : 0)) return "modifiers-failed";
            return member.getName();
        }
        try { Object missing = null; return missing.hashCode() == 0 ? "bad" : "bad"; }
        catch (NullPointerException expected) { return "null"; }
    }
}
