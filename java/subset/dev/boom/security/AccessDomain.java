package dev.boom.security;

// Metadata identities for VM domain-binding tests; these methods are not guest security code.
public final class AccessDomain {
    public static final class A { public static int value() { return 1; } }
    public static final class B { public static int value() { return 2; } }
}
