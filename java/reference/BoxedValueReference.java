import java.nio.file.*;
import java.nio.charset.StandardCharsets;

// Development oracle: constructor/accessor bodies, never a game execution path.
@SuppressWarnings("removal")
public final class BoxedValueReference {
    public static void main(String[] args) throws Exception {
        try (var reader=Files.newBufferedReader(Path.of(args[0]),StandardCharsets.US_ASCII)) {
            for (String line; (line=reader.readLine())!=null;) {
                String[] fields=line.split("\t");long bits=Long.parseUnsignedLong(fields[1],16);
                long result=switch(fields[0]) {
                    case "Boolean" -> new Boolean((bits&1)!=0).booleanValue()?1:0;
                    case "Byte" -> Integer.toUnsignedLong(new Byte((byte)bits).byteValue());
                    case "Short" -> Integer.toUnsignedLong(new Short((short)bits).shortValue());
                    case "Character" -> new Character((char)bits).charValue();
                    case "Integer" -> Integer.toUnsignedLong(new Integer((int)bits).intValue());
                    case "Long" -> new Long(bits).longValue();
                    case "Float" -> Integer.toUnsignedLong(Float.floatToRawIntBits(new Float(Float.intBitsToFloat((int)bits)).floatValue()));
                    case "Double" -> Double.doubleToRawLongBits(new Double(Double.longBitsToDouble(bits)).doubleValue());
                    default -> throw new IllegalArgumentException(fields[0]);
                };
                System.out.println(Long.toUnsignedString(result,16));
            }
        }
    }
}
