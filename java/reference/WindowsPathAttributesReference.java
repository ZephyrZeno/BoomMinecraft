import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.attribute.BasicFileAttributes;
import java.nio.file.attribute.FileTime;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

// Read-only oracle for the standalone assembly kernel. Executed only in tests.
public final class WindowsPathAttributesReference {
    private static long windowsTicks(FileTime time) {
        var instant = time.toInstant();
        return (instant.getEpochSecond() + 11_644_473_600L) * 10_000_000L + instant.getNano() / 100;
    }

    public static void main(String[] args) throws Exception {
        var type = Class.forName("sun.nio.fs.WindowsFileAttributes");
        var attributes = type.getDeclaredField("fileAttrs");
        var tag = type.getDeclaredField("reparseTag");
        attributes.setAccessible(true);
        tag.setAccessible(true);
        var paths = Files.readAllLines(Path.of(args[0]), StandardCharsets.UTF_8);
        for (int i = 0; i < paths.size(); i++) {
            Path path = Path.of(paths.get(i));
            for (int follow = 0; follow <= 1; follow++) {
                LinkOption[] options = follow == 1 ? new LinkOption[0] : new LinkOption[]{LinkOption.NOFOLLOW_LINKS};
                boolean regular = Files.isRegularFile(path, options);
                try {
                    var value = Files.readAttributes(path, BasicFileAttributes.class, options);
                    int bits = (value.isRegularFile() ? 1 : 0) | (value.isDirectory() ? 2 : 0)
                            | (value.isSymbolicLink() ? 4 : 0) | (value.isOther() ? 8 : 0);
                    System.out.printf(Locale.ROOT, "%d %d %b OK %d %d %d %d %d %d %d%n", i, follow, regular,
                            Integer.toUnsignedLong(attributes.getInt(value)), Integer.toUnsignedLong(tag.getInt(value)),
                            windowsTicks(value.creationTime()), windowsTicks(value.lastAccessTime()),
                            windowsTicks(value.lastModifiedTime()), value.size(), bits);
                } catch (IOException error) {
                    System.out.printf(Locale.ROOT, "%d %d %b ERROR %s%n", i, follow, regular,
                            error.getClass().getSimpleName());
                }
            }
        }
    }
}
