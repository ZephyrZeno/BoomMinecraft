import dev.boom.threadrun.RunTask;
import java.io.DataOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ThreadRunReference {
    public static void main(String[] args) throws Exception {
        try (var out = new DataOutputStream(Files.newOutputStream(Path.of(args[0])))) {
            for (int i = 0; i < 512; i++) {
                int value = i < 4 ? new int[]{0, -1, Integer.MIN_VALUE, Integer.MAX_VALUE}[i] : i * 1199540897;
                int divisor = i % 19 - 9;
                RunTask task = new RunTask(Thread.currentThread(), value, divisor);
                Thread target = new Thread(task);
                try { target.run(); } catch (ArithmeticException exception) { task.failures++; }
                out.writeInt(value); out.writeInt(divisor); out.writeLong(task.sum);
                out.writeInt(task.calls); out.writeInt(task.failures); out.writeBoolean(task.matched);
            }
        }
    }
}
