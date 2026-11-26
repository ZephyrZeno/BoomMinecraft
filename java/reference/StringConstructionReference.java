import dev.boom.construction.ConstructProgram;
import java.io.BufferedReader;
import java.io.InputStreamReader;

// JVM oracle only; not shipped as native game code.
public final class StringConstructionReference {
    public static void main(String[] args) throws Exception {
        var path = (args.length == 0 || args[0].equals("all")) ? null : Class.forName("sun.net.www.ParseUtil").getDeclaredMethod("encodePath", String.class, int.class, char.class);
        if (path != null) path.setAccessible(true);
        var reader = new BufferedReader(new InputStreamReader(System.in));
        String line;
        while ((line = reader.readLine()) != null) {
            String[] fields = line.split(" ");
            char[] input = null;
            if (!fields[0].equals("null")) {
                String[] units = fields[0].equals("-") ? new String[0] : fields[0].split(",");
                input = new char[units.length];
                for (int i = 0; i < units.length; i++) input[i] = (char)Integer.parseUnsignedInt(units[i], 16);
            }
            int offset = Integer.parseUnsignedInt(fields[1], 16), count = Integer.parseUnsignedInt(fields[2], 16);
            try {
                String value = path == null ? (args.length > 0 && args[0].equals("all") ? ConstructProgram.valueAll(input, offset, count) : ConstructProgram.value(input, offset, count))
                        : (String)path.invoke(null, input == null ? null : new String(input), offset, (char)count);
                var output = new StringBuilder("v ");
                for (int i = 0; i < value.length(); i++) output.append(String.format("%04x", (int)value.charAt(i)));
                System.out.println(output);
            } catch (Throwable failure) {
                if (failure instanceof java.lang.reflect.InvocationTargetException) failure = failure.getCause();
                System.out.println("e " + failure.getClass().getName());
            }
        }
    }
}
