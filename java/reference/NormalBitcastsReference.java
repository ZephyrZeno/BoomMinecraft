import java.nio.file.Files;
import java.nio.file.Path;

/** JVM-only oracle. NaN canonicalization remains original Java behavior. */
public class NormalBitcastsReference {
    public static void main(String[] args) throws Exception {
        for(String line:Files.readAllLines(Path.of(args[0]))) {
            String[] p=line.split("\t");long bits=Long.parseUnsignedLong(p[1],16);
            if(p[0].equals("F")) {
                float value=Float.intBitsToFloat((int)bits);
                System.out.printf("F\t%08x\t%08x\t%08x%n",(int)bits,Float.floatToRawIntBits(value),Float.floatToIntBits(value));
            } else {
                double value=Double.longBitsToDouble(bits);
                System.out.printf("D\t%016x\t%016x\t%016x%n",bits,Double.doubleToRawLongBits(value),Double.doubleToLongBits(value));
            }
        }
    }
}
