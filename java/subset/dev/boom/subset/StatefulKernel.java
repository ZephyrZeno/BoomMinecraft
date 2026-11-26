package dev.boom.subset;

public final class StatefulKernel {
    private static int value = 7;
    public static int read() { return value; }
}
