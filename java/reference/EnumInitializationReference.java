import java.nio.file.*;
import java.nio.charset.StandardCharsets;

// Reference only. Initializing these JDK enums does not execute Minecraft.
public final class EnumInitializationReference {
    public static void main(String[] args) throws Exception {
        for (String line:Files.readAllLines(Path.of(args[0]),StandardCharsets.US_ASCII)) {
            String name=line.split("\t")[0];Class<?> type=Class.forName(name.replace('/','.'),true,ClassLoader.getPlatformClassLoader());
            for (Object value:type.getEnumConstants()) {
                Enum<?> e=(Enum<?>)value;System.out.println(name+"\t"+e.name()+"\t"+e.ordinal());
            }
        }
        try (var writer=Files.newBufferedWriter(Path.of(args[2]),StandardCharsets.US_ASCII)) {
            for (String line:Files.readAllLines(Path.of(args[1]),StandardCharsets.US_ASCII)) {
                String[] parts=line.split("\t");Class<?> type=Class.forName(parts[0].replace('/','.'),true,ClassLoader.getPlatformClassLoader());
                Object value=type.getField(parts[2]).get(null);String encoded;
                if (value instanceof String text) {
                    StringBuilder units=new StringBuilder();for(int i=0;i<text.length();i++)units.append(String.format("%04x",(int)text.charAt(i)));encoded=units.toString();
                } else {
                    long bits=switch(parts[4]) {
                        case "Z" -> (Boolean)value?1:0;
                        case "C" -> (Character)value;
                        case "F" -> Integer.toUnsignedLong(Float.floatToRawIntBits((Float)value));
                        case "D" -> Double.doubleToRawLongBits((Double)value);
                        case "J" -> (Long)value;
                        default -> Integer.toUnsignedLong(((Number)value).intValue());
                    };encoded=Long.toUnsignedString(bits,16);
                }
                writer.write(encoded);writer.newLine();
            }
        }
    }
}
