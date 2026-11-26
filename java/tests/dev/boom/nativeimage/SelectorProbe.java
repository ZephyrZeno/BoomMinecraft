package dev.boom.nativeimage;

import java.nio.channels.Pipe;
import java.nio.channels.Selector;

/** Distinguishes host selector failures from Minecraft or AOT failures. */
public final class SelectorProbe {
    public static void main(String[] args) throws Exception {
        try (Selector selector = Selector.open()) {
            Pipe pipe = Pipe.open();
            pipe.source().close();
            pipe.sink().close();
            System.out.println(selector.getClass().getName());
        }
    }
}
