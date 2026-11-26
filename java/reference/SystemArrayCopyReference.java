import java.lang.reflect.Array;

// Independent JVM oracle only. Native runtime tests consume its snapshots.
public final class SystemArrayCopyReference {
    private static final Object O=new Object();
    private static final String A=new String("a"),B=new String("b");
    private static Object primitive(int kind,boolean dest){
        Object value=switch(kind){
            case 0->new boolean[]{true,false,true,true,false,false,true,false};
            case 1->new byte[]{-128,127,1,-3,0,16,64,-1};
            case 2->new char[]{0,65535,55296,1024,1,32,1000,2000};
            case 3->new short[]{-32768,32767,1,-3,0,16,2000,-1};
            case 4->new int[]{0x80000000,0x7fffffff,1,-3,0,16,2000,-1};
            case 5->new long[]{Long.MIN_VALUE,Long.MAX_VALUE,1,-3,0,16,2000,-1};
            case 6->new float[]{Float.intBitsToFloat(0x7fc00001),-0.0f,1.25f,-3,0,16,2000,-1};
            case 7->new double[]{Double.longBitsToDouble(0x7ff8000000000001L),-0.0,1.25,-3,0,16,2000,-1};
            default->throw new AssertionError();
        };
        if(dest)for(int i=0;i<4;i++){Object x=Array.get(value,i);Array.set(value,i,Array.get(value,7-i));Array.set(value,7-i,x);}
        return value;
    }
    private static Object make(int kind,boolean dest){
        if(kind<8)return primitive(kind,dest);
        return switch(kind){
            case 8->dest?new String[]{B,A,null,B,A,B,null,A}:new String[]{A,null,B,A,B,null,A,B};
            case 9->dest?new Object[]{O,O,O,O,O,O,O,O}:new String[]{A,null,B,A,B,null,A,B};
            case 10->dest?new String[]{B,B,B,B,B,B,B,B}:new Object[]{A,null,B,O,A,null,B,A};
            case 11->dest?new String[]{B,B,B,B,B,B,B,B}:new Object[8];
            case 12->primitive(dest?1:0,dest);
            case 13->primitive(dest?5:4,dest);
            case 14->dest?new Object[8]:primitive(4,false);
            case 15->dest?primitive(4,true):O;
            case 16->dest?O:primitive(4,false);
            case 17->dest?primitive(4,true):null;
            case 18->dest?null:primitive(4,false);
            case 19->dest?null:O;
            default->throw new AssertionError();
        };
    }
    private static String snapshot(Object value){
        if(value==null)return "-";
        if(!value.getClass().isArray())return "object";
        StringBuilder out=new StringBuilder();
        if(value instanceof Object[] refs){for(Object x:refs)out.append(x==null?'0':x==A?'1':x==O?'2':x==B?'3':'?');return out.toString();}
        for(int i=0;i<Array.getLength(value);i++){
            long bits;int bytes;
            if(value instanceof boolean[] v){bits=v[i]?1:0;bytes=1;}
            else if(value instanceof byte[] v){bits=v[i];bytes=1;}
            else if(value instanceof char[] v){bits=v[i];bytes=2;}
            else if(value instanceof short[] v){bits=v[i];bytes=2;}
            else if(value instanceof int[] v){bits=v[i];bytes=4;}
            else if(value instanceof long[] v){bits=v[i];bytes=8;}
            else if(value instanceof float[] v){bits=Float.floatToRawIntBits(v[i]);bytes=4;}
            else{bits=Double.doubleToRawLongBits(((double[])value)[i]);bytes=8;}
            for(int b=0;b<bytes;b++)out.append(String.format("%02x",(bits>>>(b*8))&255));
        }
        return out.toString();
    }
    public static void main(String[] args){
        int[][] ranges={{0,0,0},{0,0,8},{0,2,6},{2,0,6},{7,7,1},{8,8,0},{-1,0,0},{0,-1,0},{0,0,-1},{9,0,0},
                        {Integer.MAX_VALUE,0,0},{0,Integer.MAX_VALUE,0},{0,0,Integer.MAX_VALUE},{7,7,2},{Integer.MIN_VALUE,Integer.MIN_VALUE,0}};
        for(int kind=0;kind<20;kind++)for(int alias=0;alias<2;alias++)for(int[] r:ranges){
            Object source=make(kind,false),destination=alias==1?source:make(kind,true);int error=0;
            try{System.arraycopy(source,r[0],destination,r[1],r[2]);}
            catch(NullPointerException e){error=4;}catch(ArrayStoreException e){error=6;}catch(IndexOutOfBoundsException e){error=5;}
            System.out.println(kind+"\t"+alias+"\t"+r[0]+"\t"+r[1]+"\t"+r[2]+"\t"+error+"\t"+snapshot(source)+"\t"+snapshot(destination));
        }
    }
}
