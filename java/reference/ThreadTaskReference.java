import dev.boom.threads.ThreadTask;
import java.io.DataOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ThreadTaskReference {
    public static void main(String[] args) throws Exception {
        var states=new ThreadTask.State[64];var results=new long[64];var kinds=new int[64];
        Thread[] workers=new Thread[64];
        for(int i=0;i<64;i++){
            final int n=i;states[n]=ThreadTask.create(n,n%9==0?0:n%7+1);
            workers[n]=new Thread(()->{
                try{results[n]=ThreadTask.run(states[n]);}
                catch(ArithmeticException e){kinds[n]=1;ThreadTask.onFailure(states[n]);}
                finally{ThreadTask.onExit(states[n]);}
            });workers[n].start();
        }
        for(Thread worker:workers)worker.join();
        try(var out=new DataOutputStream(Files.newOutputStream(Path.of(args[0])))){
            for(int n=0;n<64;n++){out.writeLong(results[n]);out.writeInt(kinds[n]);out.writeLong(ThreadTask.summary(states[n]));}
        }
    }
}
