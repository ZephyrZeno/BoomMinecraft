package dev.boom.properties;
import java.io.DataOutputStream;
import java.lang.reflect.Field;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.TreeMap;

/** Development oracle only; the native image executes the original Raw constructor in ASM. */
public final class RawReference {
    public static void main(String[] args) throws Exception {
        Class<?> raw = Class.forName("jdk.internal.util.SystemProps$Raw");
        var constructor = raw.getDeclaredConstructor(); constructor.setAccessible(true);
        Field values = raw.getDeclaredField("platformProps"); values.setAccessible(true);
        String[] snapshot = (String[])values.get(constructor.newInstance());
        var names = new TreeMap<Integer,String>();
        for (Field field : raw.getDeclaredFields()) {
            if (!field.getName().endsWith("_NDX")) continue;
            field.setAccessible(true);names.put(field.getInt(null),field.getName());
        }
        if (names.size() != snapshot.length) throw new IllegalStateException("Raw index count mismatch");
        try (var out = new DataOutputStream(Files.newOutputStream(Path.of(args[0])))) {
            out.writeInt(0x50524f50);out.writeInt(1);out.writeInt(snapshot.length);
            for (int i = 0; i < snapshot.length; i++) {
                out.writeUTF(names.get(i));String value = snapshot[i];
                out.writeInt(value == null ? -1 : value.length());
                if (value != null) for (int j = 0; j < value.length(); j++) out.writeChar(value.charAt(j));
            }
        }
        System.out.println("Original Raw constructor; indexed platform values=" + snapshot.length);
    }
}
