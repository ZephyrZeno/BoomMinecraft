package dev.boom.threadrun;

public final class RunTask implements Runnable {
    public Thread expected;
    public int value;
    public int divisor;
    public long sum;
    public int calls;
    public int failures;
    public boolean matched;

    public RunTask(Thread expected, int value, int divisor) {
        this.expected = expected;
        this.value = value;
        this.divisor = divisor;
    }

    public void run() {
        long next = (long) value * 6364136223846793005L + 1442695040888963407L;
        sum += next / divisor;
        matched = Thread.currentThread() == expected;
        calls++;
    }
}
