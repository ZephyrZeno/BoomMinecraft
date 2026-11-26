package dev.boom.strings;
public final class TextB {
    public static String pick(int which) {
        return switch(which&7) {
            case 0 -> "";
            case 1 -> "hello";
            case 2 -> "A\0B";
            case 3 -> "\u4e16\u754c\ud83d\ude80";
            case 4 -> "\ud800x\udfff";
            case 5 -> "Aa";
            case 6 -> "BB";
            default -> "\u00ff\u0100\uffff";
        };
    }
}
