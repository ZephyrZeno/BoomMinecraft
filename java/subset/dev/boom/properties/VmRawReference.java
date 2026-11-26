package dev.boom.properties;
import java.util.Base64;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
/** JVM development oracle, never included in the native game runtime. */
public final class VmRawReference {
    public static void main(String[] args) throws Exception {
        Class<?> raw = Class.forName("jdk.internal.util.SystemProps$Raw");
        var method = raw.getDeclaredMethod("vmProperties"); method.setAccessible(true);
        String[] array = (String[])method.invoke(null);
        var values = new HashMap<String,String>();
        for(int i=0;i<array.length;) {
            String key=array[i++]; if(key==null) break;
            if(i==array.length) throw new AssertionError("Unpaired native VM key");
            String value=array[i++]; values.put(key,value==null?"":value);
        }
        for(String key:args) {
            String value=values.get(key); if(value==null) throw new AssertionError("Missing "+key);
            System.out.println(Base64.getEncoder().encodeToString(value.getBytes(StandardCharsets.UTF_16BE)));
        }
    }
}
