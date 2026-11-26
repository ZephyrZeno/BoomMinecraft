import java.nio.file.Files;
import java.nio.file.Path;
public final class ThreadNativesReference {
    public static void main(String[] args) throws Exception {
        if(args[0].equals("bad")){Class.forName("dev.boom.threadnative.BadRegistration").getMethod("run").invoke(null);return;}
        Thread.onSpinWait();var marker=Thread.class.getDeclaredField("NEW_THREAD_BINDINGS");marker.setAccessible(true);
        var empty=Thread.class.getDeclaredField("EMPTY_STACK_TRACE");empty.setAccessible(true);
        boolean same=marker.get(null)==Thread.class;int length=((Object[])empty.get(null)).length;
        if(!same||length!=0)throw new AssertionError("Thread bootstrap fields changed");
        Files.writeString(Path.of(args[0]),"{\"marker_is_Thread_class\":true,\"empty_stack_trace_length\":0}");
    }
}
