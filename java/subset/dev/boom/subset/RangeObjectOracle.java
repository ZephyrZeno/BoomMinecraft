package dev.boom.subset;
import com.mojang.brigadier.context.StringRange;
import java.io.BufferedReader;
import java.io.InputStreamReader;

/** Actual locked Brigadier factories on the JVM; reference testing only. */
public final class RangeObjectOracle {
    public static void main(String[] args) throws Exception {
        var reader=new BufferedReader(new InputStreamReader(System.in));String line;
        while((line=reader.readLine())!=null) {
            var parts=line.split(" ");int start=(int)Long.parseUnsignedLong(parts[1],16);
            StringRange range=switch(parts[0]) {
                case "at" -> StringRange.at(start);
                case "between" -> StringRange.between(start,(int)Long.parseUnsignedLong(parts[2],16));
                default -> throw new IllegalArgumentException("Unknown factory");
            };
            System.out.println(range.getStart()+" "+range.getEnd());
        }
    }
}
