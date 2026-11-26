import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.IdentityHashMap;

// Development JVM oracle only; never used by the delivered game runtime.
public final class ClassLoaderAssertionsReference {
    private static Object field(Object receiver, String name) throws Exception {
        Field field = receiver.getClass().getDeclaredField(name);
        field.setAccessible(true);
        return field.get(receiver);
    }

    private static String quote(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (c == '\\' || c == '"') out.append('\\').append(c);
            else if (c < 32 || Character.isSurrogate(c))
                out.append(String.format("\\u%04x", (int)c));
            else out.append(c);
        }
        return out.append('"').toString();
    }

    private static String strings(String[] values) {
        StringBuilder out = new StringBuilder("[");
        for (int i = 0; i < values.length; i++) {
            if (i != 0) out.append(',');
            out.append(values[i] == null ? "null" : quote(values[i]));
        }
        return out.append(']').toString();
    }

    private static String snapshot(Object directives, IdentityHashMap<Object, Boolean> seen)
            throws Exception {
        Object classes = field(directives, "classes");
        Object classEnabled = field(directives, "classEnabled");
        Object packages = field(directives, "packages");
        Object packageEnabled = field(directives, "packageEnabled");
        if (classes.getClass() != String[].class || packages.getClass() != String[].class ||
                classEnabled.getClass() != boolean[].class || packageEnabled.getClass() != boolean[].class)
            throw new AssertionError("Directive array types changed");
        for (Object object : new Object[]{directives, classes, classEnabled, packages, packageEnabled})
            if (seen.put(object, true) != null) throw new AssertionError("Snapshot objects alias");
        if (((String[])classes).length != ((boolean[])classEnabled).length ||
                ((String[])packages).length != ((boolean[])packageEnabled).length)
            throw new AssertionError("Directive name/value lengths differ");
        return "{\"classes\":" + strings((String[])classes) +
                ",\"classEnabled\":" + java.util.Arrays.toString((boolean[])classEnabled) +
                ",\"packages\":" + strings((String[])packages) +
                ",\"packageEnabled\":" + java.util.Arrays.toString((boolean[])packageEnabled) +
                ",\"deflt\":" + field(directives, "deflt") + "}";
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 0) throw new IllegalArgumentException("No game or account inputs accepted");
        Method retrieve = ClassLoader.class.getDeclaredMethod("retrieveDirectives");
        retrieve.setAccessible(true);
        IdentityHashMap<Object, Boolean> seen = new IdentityHashMap<>();
        String first = snapshot(retrieve.invoke(null), seen);
        String second = snapshot(retrieve.invoke(null), seen);
        if (!first.equals(second)) throw new AssertionError("Frozen VM assertion options changed");
        System.out.println("{\"directives\":" + first +
                ",\"application_probe\":" + ClassLoaderAssertionsReference.class.desiredAssertionStatus() +
                ",\"system_probe\":" + Object.class.desiredAssertionStatus() +
                ",\"independent_snapshot_objects\":" + seen.size() + "}");
    }
}
