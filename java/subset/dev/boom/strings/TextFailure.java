package dev.boom.strings;
public final class TextFailure {
    public static final String CONST="A\0B";
    public static String partial=CONST;
    public static int value=CONST.charAt(CONST.length());
}
