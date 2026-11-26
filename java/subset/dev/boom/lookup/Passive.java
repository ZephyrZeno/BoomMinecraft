package dev.boom.lookup;
public interface Passive {
    Object token=mark();
    private static Object mark(){Counters.mask|=16;return new Object();}
}
