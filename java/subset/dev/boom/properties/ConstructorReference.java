package dev.boom.properties;
import java.io.BufferedReader;
import java.io.InputStreamReader;

/** Independent JVM constructor and partial-escape oracle; never translated. */
public final class ConstructorReference {
    public static void main(String[] args) throws Exception {
        var reader = new BufferedReader(new InputStreamReader(System.in));
        for (String line; (line = reader.readLine()) != null;) {
            String[] w = line.split(" ");
            try {
                ConstructorProgram value = w[0].equals("default") ? new ConstructorProgram()
                    : new ConstructorProgram((int)Long.parseUnsignedLong(w[1],16),Long.parseUnsignedLong(w[2],16),Double.longBitsToDouble(Long.parseUnsignedLong(w[3],16)));
                if (value != value.self || value != ConstructorProgram.escaped) throw new IllegalStateException("Constructor identity lost");
                System.out.printf("v %08x %016x %016x %08x %d%n",value.value,value.wide,Double.doubleToRawLongBits(value.decimal),value.base,ConstructorProgram.initializationCount);
            } catch (IllegalArgumentException failure) {
                ConstructorProgram value = ConstructorProgram.escaped;
                if (value.self != value) throw new IllegalStateException("Partial constructor escape lost");
                System.out.printf("e java.lang.IllegalArgumentException %08x %016x %016x %08x %d%n",value.value,value.wide,Double.doubleToRawLongBits(value.decimal),value.base,ConstructorProgram.initializationCount);
            }
        }
    }
}
