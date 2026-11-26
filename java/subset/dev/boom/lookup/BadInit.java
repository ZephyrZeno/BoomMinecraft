package dev.boom.lookup;
public class BadInit {
    static {Counters.mask|=128;if(fail())throw new Boom();}
    private static boolean fail(){return true;}
    public static class Boom extends RuntimeException {}
}
