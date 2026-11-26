package dev.boom.mirrors;

public final class ClassEntry {
    static Class<?> select(int which) {
        switch (which & 15) {
            case 0: return Object.class;
            case 1: return String.class;
            case 2: return Class.class;
            case 3: return java.io.File.class;
            case 4: return Integer.class;
            case 5: return CharSequence.class;
            case 6: return Child.class;
            case 7: return Marker.class;
            case 8: return int[].class;
            case 9: return String[][].class;
            case 10: return int[][].class;
            case 11: return byte[].class;
            case 12: return boolean[].class;
            case 13: return java.io.Serializable.class;
            case 14: return ClassFailure.class;
            default: return Base.class;
        }
    }
    public static int nameHash(int which) { return select(which).getName().hashCode(); }
    public static int mirrorMix(int seed, int other) { return java.io.File.class.getName().hashCode() ^ seed ^ other; }
    public static int flags(int which) {
        Class<?> c = select(which);
        return (c.isArray() ? 1 : 0) | (c.isPrimitive() ? 2 : 0) | (c.isInterface() ? 4 : 0);
    }
    public static int parent(int which) {
        Class<?> c = select(which).getSuperclass();
        return c == null ? -1 : c.getName().hashCode();
    }
    public static int component(int which) {
        Class<?> c = select(which).getComponentType();
        return c == null ? -1 : c.getName().hashCode() ^ (c.isPrimitive() ? 1 : 0);
    }
    public static int primitiveRelation(int which) {
        Class<?> c = int[].class.getComponentType();
        return (c.isPrimitive() ? 1 : 0) | (c.getSuperclass() == null ? 2 : 0)
            | (c.getComponentType() == null ? 4 : 0) | (c.isArray() ? 8 : 0)
            | (c.isInterface() ? 16 : 0) | (c.isAssignableFrom(c) ? 32 : 0)
            | (select(which).isAssignableFrom(c) ? 64 : 0)
            | (c.isAssignableFrom(select(which)) ? 128 : 0);
    }
    public static int assignable(int target, int source) { return select(target).isAssignableFrom(select(source)) ? 1 : 0; }
    public static int identity(int which) { return select(which) == select(which + 16) ? 1 : 0; }
    public static int array(int count, int index, int which) {
        Class<?>[] values = new Class<?>[count];
        values[index] = select(which);
        return values[index].getName().hashCode() ^ values.length;
    }
    public static int nullElement(int count, int index) { Class<?>[] values = new Class<?>[count]; return values[index].getName().length(); }
    public static int nullReceiver(int which) { Class<?> c = null; return c.isAssignableFrom(select(which)) ? 1 : 0; }
    public static int nullArgument(int which) { return select(which).isAssignableFrom(null) ? 1 : 0; }
    public static int state(int index) { return ClassState.values[index].getName().hashCode() ^ (ClassState.value == java.io.File.class ? 1 : 0); }
    public static int unsupportedReflection() { return String.class.getDeclaredMethods().length; }
    public static int primitiveField() { return int.class.getName().length(); }
}
