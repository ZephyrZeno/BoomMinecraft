import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.lang.reflect.Array;
import java.nio.file.Files;
import java.nio.file.Path;
// JVM oracle only; never linked into the native game runtime.
public final class CharacterReference {
    static void writeArray(DataOutputStream out,Object array,int depth)throws Exception {
        int n=Array.getLength(array);out.writeInt(n);
        for(int i=0;i<n;i++) {
            if(depth==1)out.writeChar(Array.getChar(array,i));
            else writeArray(out,Array.get(array,i),depth-1);
        }
    }
    public static void main(String[] args)throws Exception {
        byte[] result=new byte[0x110000+520];
        for(int cp=0;cp<0x110000;cp++)result[cp]=(byte)Character.getType(cp);
        int[] edge={-1,Integer.MIN_VALUE,Integer.MAX_VALUE,0x110000,0x110001,0x3fffffff,0x7ffffffe,0x80000001};
        for(int i=0;i<8;i++)result[0x110000+i]=(byte)Character.getType(edge[i]);
        int x=0x45004500;for(int i=0;i<512;i++){x=x*1664525+1013904223;result[0x110008+i]=(byte)Character.getType(x);}
        Files.write(Path.of(args[0]),result);
        var f=Class.forName("java.lang.CharacterData00").getDeclaredField("charMap");f.setAccessible(true);
        var bytes=new ByteArrayOutputStream();try(var out=new DataOutputStream(bytes)){writeArray(out,f.get(null),3);}
        Files.write(Path.of(args[1]),bytes.toByteArray());
    }
}
