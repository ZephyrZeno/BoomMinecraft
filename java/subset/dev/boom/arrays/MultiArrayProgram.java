package dev.boom.arrays;

public final class MultiArrayProgram {
    static int initialized;
    static int[][][] saved;
    public static Object factory(int which) {
        switch(which & 15) {
            case 0: return new boolean[2][3];
            case 1: return new byte[2][3];
            case 2: return new char[2][3];
            case 3: return new short[2][3];
            case 4: return new int[2][3];
            case 5: return new long[2][3];
            case 6: return new float[2][3];
            case 7: return new double[2][3];
            case 8: return new String[2][3][4];
            case 9: return new Class<?>[2][3][];
            case 10: return new Dormant[2][3];
            default: return new Object[2][3][4];
        }
    }
    public static long primitives(int value, int kind) {
        int x=value&3,y=(value>>>2)&3;
        long base=x*100+y*10;
        if(x==0 || y==0) {
            switch(kind&7) {
                case 0: return new boolean[x][y].length*100+y*10;
                case 1: return new byte[x][y].length*100+y*10;
                case 2: return new char[x][y].length*100+y*10;
                case 3: return new short[x][y].length*100+y*10;
                case 4: return new int[x][y].length*100+y*10;
                case 5: return new long[x][y].length*100+y*10;
                case 6: return new float[x][y].length*100+y*10;
                default: return new double[x][y].length*100+y*10;
            }
        }
        switch(kind&7) {
            case 0: { boolean[][] a=new boolean[x][y];a[x-1][y-1]=(value&16)!=0;return base+(a[x-1][y-1]?1:0); }
            case 1: { byte[][] a=new byte[x][y];a[x-1][y-1]=(byte)value;return base+a[x-1][y-1]; }
            case 2: { char[][] a=new char[x][y];a[x-1][y-1]=(char)value;return base+a[x-1][y-1]; }
            case 3: { short[][] a=new short[x][y];a[x-1][y-1]=(short)value;return base+a[x-1][y-1]; }
            case 4: { int[][] a=new int[x][y];a[x-1][y-1]=value;return base+a[x-1][y-1]; }
            case 5: { long[][] a=new long[x][y];a[x-1][y-1]=((long)value<<32)|0x12345678L;return base+a[x-1][y-1]; }
            case 6: { float[][] a=new float[x][y];a[x-1][y-1]=Float.intBitsToFloat(value);return base+Integer.toUnsignedLong(Float.floatToRawIntBits(a[x-1][y-1])); }
            default: { double[][] a=new double[x][y];a[x-1][y-1]=Double.longBitsToDouble(((long)value<<32)|0x12345678L);return base+Double.doubleToRawLongBits(a[x-1][y-1]); }
        }
    }
    public static int jagged(int value) {
        char[][][] a={{{'a','b'},{'c'}},null,{{'x'}}};
        a[0][0][1]=(char)value;
        char[][][] b=a.clone();
        return b.length*100+b[0].length*10+b[0][0].length+b[0][0][1]+(b[0]==a[0]?1000:0);
    }
    public static int references(int value) {
        Object[][] a=new String[2][3];
        a[0][0]="x";
        Object[][] b=a.clone();
        int result=a!=b && a[0]==b[0] && a.getClass()==String[][].class ? 1:0;
        b[0][1]="y";
        if(a[0][1]=="y" && b[0].getClass()==String[].class)result+=2;
        b[1]=new String[3];
        if(a[1]!=b[1])result+=4;
        try { a[0]=new Object[3]; } catch(ArrayStoreException expected){ result+=8; }
        Object[][] c=new Object[2][];
        c[0]=new String[]{"ok"};c[1]=new Object[]{new Object()};
        String[][] d=new String[2][];
        try { System.arraycopy(c,0,d,0,2); } catch(ArrayStoreException expected){if(d[0]==c[0] && d[1]==null)result+=16;}
        return result;
    }
    public static int partial(int ignored) {
        Dormant[][][] a=new Dormant[2][3][];
        return a.length*100+a[0].length*10+(a[0][0]==null?7:0)+initialized;
    }
    public static int negative(int mode) {
        try { return new int[(mode&1)==0?0:2][-1].length; }
        catch(NegativeArraySizeException expected){ return 83; }
    }
    public static int nullAndBounds(int mode) {
        int[][] a=new int[2][];
        try { if((mode&1)==0)return a[0].length;return a[-1].length; }
        catch(NullPointerException expected){return 31;}
        catch(ArrayIndexOutOfBoundsException expected){return 53;}
    }
    public static int fullHeap(int mode) {
        if(saved==null)saved=new int[2][2][2];
        if((mode&1)==0)return saved[1][1].length;
        try { return new int[2][2][2].length; } catch(OutOfMemoryError expected){return 97;}
    }
    private static int sum(int[][][] a) {
        int s=0;for(int i=0;i<a.length;i++)for(int j=0;j<a[i].length;j++)for(int k=0;k<a[i][j].length;k++)s+=a[i][j][k];return s;
    }
    public static int parallel(int value) {
        int[][][] a=new int[2][3][4];
        for(int i=0;i<a.length;i++)for(int j=0;j<a[i].length;j++)for(int k=0;k<a[i][j].length;k++)a[i][j][k]=value+i*31+j*7+k;
        return sum(a);
    }
}
final class Dormant { static { MultiArrayProgram.initialized+=7; } }
