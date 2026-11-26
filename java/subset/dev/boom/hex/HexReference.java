package dev.boom.hex;
import java.io.*;
import java.util.*;
/** Independent JVM oracle: raw bits and every output UTF16 unit. */
public final class HexReference {
    static void row(DataOutputStream out,int width,long bits) throws IOException {
        String s=width==32?Integer.toHexString((int)bits):Long.toHexString(bits);
        out.writeInt(width);out.writeLong(bits);out.writeInt(s.length());out.writeChars(s);
    }
    public static void main(String[] args) throws Exception {
        try(DataOutputStream out=new DataOutputStream(new FileOutputStream(args[0]))) {
            out.writeInt(0x48455831);
            for(int width:new int[]{32,64}) {
                row(out,width,0);row(out,width,-1);
                for(int i=0;i<width;i++){long n=1L<<i;row(out,width,n);row(out,width,n-1);row(out,width,~n);row(out,width,-n);}
            }
            Random random=new Random(0x12345678);
            for(int i=0;i<4096;i++){row(out,32,random.nextLong());row(out,64,random.nextLong());}
            out.writeInt(0);
        }
    }
}
