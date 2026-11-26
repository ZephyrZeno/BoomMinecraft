package dev.boom.vm;
import jdk.internal.misc.VM;
public final class VmRegistrationProgram {
    public static long adjustment(long offset) { return VM.getNanoTimeAdjustment(offset); }
    public static int state(int ignored) { return VM.initLevel() + (VM.isBooted() ? 16 : 0) + (VM.isModuleSystemInited() ? 32 : 0); }
    public static long memory(int ignored) { return VM.maxDirectMemory(); }
}
