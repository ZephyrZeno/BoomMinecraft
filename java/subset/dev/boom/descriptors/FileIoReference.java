package dev.boom.descriptors;
import java.io.FileOutputStream;
public final class FileIoReference {
    public static void main(String[] paths) throws Exception {
        byte[] data=new byte[1024*1024];int seed=0x12345678;
        for(int i=0;i<data.length;i++){seed=seed*1664525+1013904223;data[i]=(byte)(seed>>>24);}
        try(FileOutputStream out=new FileOutputStream(paths[0])){out.write(data);out.getFD().sync();}
        try(FileOutputStream out=new FileOutputStream(paths[1],true)){
            for(int batch=0;batch<3;batch++)for(int i=0;i<2049;i++){
                byte[] record=new byte[16];int[] words={i,batch,0x12345678,i^batch^0x13579bdf};
                for(int j=0;j<4;j++)for(int k=0;k<4;k++)record[j*4+k]=(byte)(words[j]>>>(k*8));
                out.write(record);
            }
        }
    }
}
