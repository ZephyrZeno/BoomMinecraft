package dev.boom.casing;
import java.util.Locale;

/** Discovery probe until the original Locale initialization chain is supported. */
public final class LocaleBootstrap {
    public static int root(int n) { return n + Locale.ROOT.getLanguage().length(); }
    public static int systemDefault(int n) { return n + Locale.getDefault().getLanguage().length(); }
}
