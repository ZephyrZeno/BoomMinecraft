package dev.boom.threadrun;

public final class RunCalls {
    public static RunTask apply(int mode, Thread thread, RunTask task, int value, int divisor) {
        Thread.onSpinWait();
        if (mode == 0) return new RunTask(thread, value, divisor);
        if (mode == 1) {
            thread.run();
            return task;
        }
        try {
            thread.run();
        } catch (ArithmeticException exception) {
            task.failures++;
        }
        return task;
    }
}
