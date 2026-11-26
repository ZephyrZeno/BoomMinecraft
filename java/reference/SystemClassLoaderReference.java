import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

// Development oracle only; never included in the assembly game runtime.
public final class SystemClassLoaderReference {
    public static void main(String[] args) throws Exception {
        Map<String, Module> modules = new HashMap<>();
        for (String line : Files.readAllLines(Path.of(args[0]), StandardCharsets.UTF_8)) {
            String[] pair = line.split("\t", -1);
            if (pair.length != 2) throw new IllegalArgumentException("Expected module and class");
            Module module = modules.computeIfAbsent(pair[0], name ->
                ModuleLayer.boot().findModule(name).orElseThrow());
            Class<?> type = Class.forName(module, pair[1]); // Does not initialize the class.
            if (type == null || type.getModule() != module)
                throw new IllegalStateException("Class/module mismatch: " + line);
            ClassLoader loader = type.getClassLoader();
            String name;
            if (loader == null) name = "bootstrap";
            else if (loader == ClassLoader.getPlatformClassLoader()) name = "platform";
            else if (loader == ClassLoader.getSystemClassLoader()) name = "vanilla-application";
            else throw new IllegalStateException("Unexpected defining loader: " + line);
            System.out.println(pair[0] + "\t" + pair[1] + "\t" + name);
        }
    }
}
