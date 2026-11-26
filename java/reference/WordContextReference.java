import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.text.BreakIterator;
import java.util.HexFormat;
import java.util.Locale;

// Locked JVM oracle only; the game's word/case operations execute assembly.
public final class WordContextReference {
    public static void main(String[] args) throws Exception {
        if (args.length != 0 && args[0].equals("context")) {
            var cased = Class.forName("java.lang.ConditionalSpecialCasing").getDeclaredMethod("isCased", int.class);
            var combining = Class.forName("sun.text.Normalizer").getDeclaredMethod("getCombiningClass", int.class);
            cased.setAccessible(true); combining.setAccessible(true);
            byte[] data = new byte[0x220000];
            for (int cp = 0; cp < 0x110000; cp++) {
                int value = (int)combining.invoke(null, cp) | ((boolean)cased.invoke(null, cp) ? 256 : 0);
                data[cp * 2] = (byte)value; data[cp * 2 + 1] = (byte)(value >>> 8);
            }
            Files.write(Path.of(args[1]), data);
            System.out.println(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(data)));
            return;
        }
        var input = new BufferedReader(new InputStreamReader(System.in)); String line;
        while ((line = input.readLine()) != null) {
            String[] values = line.equals("-") ? new String[0] : line.split(",");
            char[] units = new char[values.length];
            for (int i = 0; i < units.length; i++) units[i] = (char)Integer.parseUnsignedInt(values[i], 16);
            var breaks = BreakIterator.getWordInstance(Locale.ROOT); breaks.setText(new String(units));
            var result = new StringBuilder().append(breaks.first()); int next;
            while ((next = breaks.next()) != BreakIterator.DONE) result.append(',').append(next);
            if(args.length!=0&&args[0].equals("boundary")) {
                result.append('|');
                for(int order=0;order<3;order++) {
                    if(order!=0)result.append('|');breaks=BreakIterator.getWordInstance(Locale.ROOT);breaks.setText(new String(units));
                    for(int i=0;i<=units.length;i++) {
                        if(order==1){breaks=BreakIterator.getWordInstance(Locale.ROOT);breaks.setText(new String(units));}
                        result.append(breaks.isBoundary(order==2?units.length-i:i)?'1':'0');
                    }
                }
            }
            System.out.println(result);
        }
    }
}
