import dev.boom.unsafe.FenceProgram;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.atomic.AtomicReference;
public final class FenceReference {
    public static void main(String[] args) throws Exception {
        int rounds = Integer.parseInt(args[0]);
        CyclicBarrier barrier = new CyclicBarrier(3);
        int[] results = new int[2];
        AtomicReference<Throwable> error = new AtomicReference<>();
        Thread[] workers = new Thread[2];
        for (int slot = 0; slot < 2; slot++) {
            final int index = slot;
            workers[slot] = new Thread(() -> {
                try { for (int i=0;i<rounds;i++) { barrier.await();results[index]=FenceProgram.run(index);barrier.await(); } }
                catch (Throwable e) { error.set(e);barrier.reset(); }
            });
            workers[slot].start();
        }
        int forbidden = 0;
        for (int i=0;i<rounds;i++) {
            FenceProgram.run(2);barrier.await();barrier.await();
            if ((results[0] | results[1]) == 0) forbidden++;
        }
        for (Thread worker : workers) worker.join();
        if (error.get()!=null) throw new AssertionError(error.get());
        if (forbidden!=0) throw new AssertionError("Forbidden store/load outcome: "+forbidden);
        System.out.println("rounds="+rounds+";forbidden=0");
    }
}
