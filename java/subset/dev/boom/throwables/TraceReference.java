package dev.boom.throwables;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

/** Independent JVM reference; never included in the translated game image. */
public final class TraceReference {
    public static void main(String[] args) throws Exception {
        BufferedReader reader = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        for (String line; (line = reader.readLine()) != null;) {
            String[] words = line.split(" ");
            String method = words[0];
            int n = (int) Long.parseUnsignedLong(words[1], 16);
            ThrowableProgram.class.getMethod(method, int.class).invoke(null, n);
            StringBuilder value = new StringBuilder();
            for (StackTraceElement frame : ThrowableProgram.last.getStackTrace()) {
                if (!frame.getClassName().startsWith("dev.boom.throwables.ThrowableProgram")) continue;
                if (value.length() != 0) value.append('|');
                value.append(frame.getClassName()).append('#').append(frame.getMethodName()).append('#')
                    .append(frame.getFileName()).append('#').append(frame.getLineNumber());
            }
            System.out.println(value);
        }
    }
}
