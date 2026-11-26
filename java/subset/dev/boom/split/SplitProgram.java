package dev.boom.split;
public final class SplitProgram {
    public static String[] split(String source, String regex, int limit, int mode) {
        if (mode == 3) return new String[] { source.trim() };
        if (mode == 0) return source.split(regex);
        if (mode == 1) return source.split(regex, limit);
        return source.splitWithDelimiters(regex, limit);
    }
}
