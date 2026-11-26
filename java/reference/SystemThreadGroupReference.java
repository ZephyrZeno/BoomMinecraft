import java.nio.file.Files;
import java.nio.file.Path;

/** Observe the original VM-only constructor in an isolated reference JVM. */
public final class SystemThreadGroupReference {
    public static void main(String[] args) throws Exception {
        var constructor=ThreadGroup.class.getDeclaredConstructor();constructor.setAccessible(true);
        Object value=constructor.newInstance();StringBuilder json=new StringBuilder("{");
        String[] names={"parent","name","groups","weaks","maxPriority","ngroups","nweaks","daemon"};
        for(String name:names){var field=ThreadGroup.class.getDeclaredField(name);field.setAccessible(true);Object item=field.get(value);if(json.length()>1)json.append(',');json.append('"').append(name).append("\":");if(item instanceof String text)json.append('"').append(text).append('"');else json.append(item);}
        json.append('}');Files.writeString(Path.of(args[0]),json);
    }
}
