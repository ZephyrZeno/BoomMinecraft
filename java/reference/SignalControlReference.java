import java.io.DataOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.lang.reflect.Method;

/** JVM registration oracle in its own process; it never raises a signal. */
public final class SignalControlReference {
    public static void main(String[] args) throws Exception {
        Class<?> owner=Class.forName("jdk.internal.misc.Signal");
        Method handle=owner.getDeclaredMethod("handle0",int.class,long.class);
        handle.setAccessible(true);
        int[] signals={2,4,6,8,11,15,21,22};
        int[] canonical={2,4,8,11,15,21,22};
        long[] saved=new long[canonical.length];
        for(int i=0;i<canonical.length;i++)saved[i]=(Long)handle.invoke(null,canonical[i],0L);
        try(var out=new DataOutputStream(Files.newOutputStream(Path.of(args[0])))){
            for(int i=0;i<4096;i++){
                int signal=signals[i%signals.length];long value=(i*17L+11)%3;
                long old=(Long)handle.invoke(null,signal,value);
                out.writeInt(signal);out.writeLong(value);out.writeLong(old);
            }
        } finally {
            for(int i=0;i<canonical.length;i++)if(saved[i]!=-1)handle.invoke(null,canonical[i],saved[i]);
        }
        try(var out=new DataOutputStream(Files.newOutputStream(Path.of(args[1])))){
            for(int number:new int[]{4,11}){
                long old=(Long)handle.invoke(null,number,0L);
                try {
                    out.writeLong((Long)handle.invoke(null,number,1L));
                    long[] values=new long[2];var failure=new java.util.concurrent.atomic.AtomicReference<Exception>();
                    Thread thread=new Thread(()->{try{values[0]=(Long)handle.invoke(null,number,2L);values[1]=(Long)handle.invoke(null,number,0L);}catch(Exception e){failure.set(e);}});
                    thread.start();thread.join();if(failure.get()!=null)throw failure.get();
                    out.writeLong(values[0]);out.writeLong(values[1]);out.writeLong((Long)handle.invoke(null,number,0L));
                } finally {handle.invoke(null,number,old);}
            }
            long old=(Long)handle.invoke(null,22,0L);
            try {
                out.writeLong((Long)handle.invoke(null,6,1L));
                long[] value=new long[1];var failure=new java.util.concurrent.atomic.AtomicReference<Exception>();
                Thread thread=new Thread(()->{try{value[0]=(Long)handle.invoke(null,22,2L);}catch(Exception e){failure.set(e);}});
                thread.start();thread.join();if(failure.get()!=null)throw failure.get();
                out.writeLong(value[0]);out.writeLong((Long)handle.invoke(null,6,0L));
            } finally {handle.invoke(null,22,old);}
        }
    }
}
