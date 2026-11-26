package dev.boom.casing;
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.nio.file.Files;
import java.nio.file.Path;

/** Development-only exhaustive Character oracle. Never linked into native games. */
public final class MappingOracle {
    public static void main(String[] args) throws Exception {
        var bytes = new ByteArrayOutputStream();
        var rows = new DataOutputStream(bytes);
        int count = 0;
        for (int cp = 0; cp <= Character.MAX_CODE_POINT; cp++) {
            int upper = Character.toUpperCase(cp), lower = Character.toLowerCase(cp);
            if (cp == upper && cp == lower) continue;
            rows.writeInt(cp); rows.writeInt(upper); rows.writeInt(lower); count++;
        }
        try (var out = new DataOutputStream(Files.newOutputStream(Path.of(args[0])))) {
            out.writeInt(0x55434331); out.writeInt(count); bytes.writeTo(out);
        }
        System.out.println("Checked 1114112 code points; mapping rows=" + count);
    }
}
