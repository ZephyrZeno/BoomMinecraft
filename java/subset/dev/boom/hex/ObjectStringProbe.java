package dev.boom.hex;
/** Discovery probes only; success here would still require native execution. */
public final class ObjectStringProbe {
    public static String defaultObject(int n) { return new Object().toString(); }
    public static String classObject(int n) { return ObjectStringProbe.class.toString(); }
}
