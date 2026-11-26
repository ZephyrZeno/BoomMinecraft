import java.lang.reflect.Field;
import java.util.Random;

// Development oracle only. It observes real JDK String storage after hashCode.
public final class JavaStringLiteralReference {
    static final Field VALUE;
    static final Field CODER;
    static {
        try {
            VALUE = String.class.getDeclaredField("value"); VALUE.setAccessible(true);
            CODER = String.class.getDeclaredField("coder"); CODER.setAccessible(true);
        } catch (ReflectiveOperationException error) { throw new ExceptionInInitializerError(error); }
    }
    static String hex(byte[] bytes) {
        StringBuilder out = new StringBuilder(bytes.length*2);
        char[] digits = "0123456789abcdef".toCharArray();
        for (byte b : bytes) { out.append(digits[(b>>>4)&15]); out.append(digits[b&15]); }
        return out.toString();
    }
    static void emit(char[] chars) throws Exception {
        String value = new String(chars);
        StringBuilder units = new StringBuilder(chars.length*4);
        char[] digits = "0123456789abcdef".toCharArray();
        for (char c : chars) for (int shift=12; shift>=0; shift-=4) units.append(digits[(c>>>shift)&15]);
        System.out.println(units+"\t"+CODER.getByte(value)+"\t"+
            Integer.toUnsignedString(value.hashCode(),16)+"\t"+hex((byte[])VALUE.get(value)));
    }
    public static void main(String[] args) throws Exception {
        if (args.length == 1) {
            try (var input = java.nio.file.Files.newBufferedReader(java.nio.file.Path.of(args[0]), java.nio.charset.StandardCharsets.US_ASCII)) {
                for (String line; (line = input.readLine()) != null;) {
                    if (line.length()%4 != 0) throw new IllegalArgumentException("Bad UTF16 input");
                    char[] chars = new char[line.length()/4];
                    for (int i=0; i<chars.length; i++) chars[i]=(char)Integer.parseInt(line.substring(i*4,i*4+4),16);
                    emit(chars);
                }
            }
            return;
        }
        emit(new char[0]);
        for (String value : new String[]{"Aa","BB","FB","Ea","Minecraft 1.21.1","世界","\0","\ud800","\udfff","\ud83d\ude00"}) emit(value.toCharArray());
        char[] longest = new char[65535]; java.util.Arrays.fill(longest, 'A'); emit(longest);
        char[] wide = new char[21845]; java.util.Arrays.fill(wide, '\u3001'); emit(wide);
        for (int c=0; c<=65535; c++) emit(new char[]{(char)c});
        Random random = new Random(0x4a534c50L);
        for (int n=0; n<4096; n++) {
            char[] chars = new char[random.nextInt(96)];
            for (int i=0; i<chars.length; i++) chars[i]=(char)random.nextInt(n%2==0?256:65536);
            emit(chars);
        }
    }
}
