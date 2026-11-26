package dev.boom.typechecks;
class MetadataOnly {
    static int unavailable = (int)System.nanoTime();
    static int failure = 1 / zero(); static int zero() { return 0; }
}
