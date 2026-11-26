package dev.boom.lowercase;
import java.util.Locale;
public final class LowercaseProgram {
    public static String lower(String value, Locale locale) {
        return value.toLowerCase(locale);
    }
}
