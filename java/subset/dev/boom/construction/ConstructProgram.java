package dev.boom.construction;

public final class ConstructProgram {
    public static String valueAll(char[] input, int unusedOffset, int unusedCount) { return new String(input); }
    public static String value(char[] input, int offset, int count) {
        return new String(input, offset, count);
    }
    public static int check(int seed, int offset, int count) {
        char[] input = seed == -1 ? null : new char[seed & 31];
        if (input != null) for (int i = 0; i < input.length; i++) input[i] = (char)(seed * 7919 + i * 1009);
        try {
            String value = new String(input, offset, count);
            String second = new String(input, offset, count);
            int flags = value != second ? 1 : 0;
            if (count != 0) {
                char first = value.charAt(0);
                input[offset] ^= 85;
                if (value.charAt(0) == first) flags |= 2;
            }
            if (value.getClass() == String.class) flags |= 4;
            if (value.equals(second)) flags |= 8;
            return value.hashCode() ^ value.length() * 65537 ^ flags;
        } catch (NullPointerException e) {
            return -4;
        } catch (StringIndexOutOfBoundsException e) {
            return -11;
        }
    }
}
