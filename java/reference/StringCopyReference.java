import java.io.*;
import java.lang.reflect.*;
import java.util.*;

public final class StringCopyReference {
    public static void main(String[] args) throws Exception {
        Method full = String.class.getDeclaredMethod("getBytes", byte[].class, int.class, byte.class);
        Method range = String.class.getDeclaredMethod("getBytes", byte[].class, int.class, int.class, byte.class, int.class);
        Method prepend = Class.forName("java.lang.StringConcatHelper").getDeclaredMethod("prepend", long.class, byte[].class, String.class);
        full.setAccessible(true); range.setAccessible(true); prepend.setAccessible(true);
        try (var input = new BufferedReader(new InputStreamReader(System.in))) {
            String line;
            while ((line = input.readLine()) != null) {
                String[] p = line.split("\\|", -1);
                int src = Integer.parseInt(p[1]), dst = Integer.parseInt(p[2]);
                int count = Integer.parseInt(p[3]), capacity = Integer.parseInt(p[4]);
                String text = null;
                if (!p[5].equals("null")) {
                    String[] units = p[5].isEmpty() ? new String[0] : p[5].split(":");
                    char[] chars = new char[units.length];
                    for (int i = 0; i < chars.length; i++) chars[i] = (char)Integer.parseInt(units[i], 16);
                    text = new String(chars);
                }
                byte[] buffer = capacity < 0 ? null : new byte[capacity];
                if (buffer != null) Arrays.fill(buffer, (byte)0x5a);
                String result;
                try {
                    long value = 0;
                    if (p[0].equals("P")) value = (Long)prepend.invoke(null, 0x100000000L + Integer.toUnsignedLong(dst + (text == null ? 0 : text.length())), buffer, text);
                    else if (p[0].equals("F")) full.invoke(text, buffer, dst, (byte)1);
                    else range.invoke(text, buffer, src, dst, (byte)1, count);
                    result = String.format("v %016x", value);
                } catch (InvocationTargetException ex) {
                    result = "e " + ex.getCause().getClass().getName();
                } catch (NullPointerException ex) {
                    result = "e java.lang.NullPointerException";
                }
                System.out.println(result + " " + (buffer == null ? "null" : HexFormat.of().formatHex(buffer)));
            }
        }
    }
}
