package dev.boom.unwind;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

/** Independent JVM oracle. Not translated or included in the native runtime. */
public final class TraceReference {
    public static void main(String[] args) throws Exception {
        var reader = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        for (String line; (line = reader.readLine()) != null;) {
            String[] words = line.split(" ");
            UnwindProgram.class.getMethod(words[0], int.class).invoke(null, (int)Long.parseUnsignedLong(words[1], 16));
            var value = new StringBuilder();
            for (StackTraceElement frame : UnwindProgram.last.getStackTrace()) {
                if (!frame.getClassName().startsWith("dev.boom.unwind.UnwindProgram")) continue;
                if (value.length() != 0) value.append('|');
                value.append(frame.getClassName()).append('#').append(frame.getMethodName()).append('#')
                    .append(frame.getFileName()).append('#').append(frame.getLineNumber());
            }
            System.out.println(value);
        }
    }
}
