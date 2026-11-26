package dev.boom.lookup;
public interface DefaultInit {
    Object token=mark();
    private static Object mark(){Counters.mask|=8;return new Object();}
    default int value(){return 1;}
}
