package dev.boom.fields;
public final class GetCharsProgram {
    public static String run(int mode) {
        String input = switch (mode/12) { case 0 -> ""; case 1 -> "abc"; case 2 -> "\0A\u00ff\u0100\ud800\udc00\ud801X"; default -> null; };
        int length=input==null?0:input.length(),begin=0,end=length,capacity=16,destination=0;
        switch (mode%12) {
            case 1 -> { end=0;capacity=0; }
            case 2 -> { begin=1;end=2;destination=1; }
            case 3 -> { begin=-1;end=0;capacity=-1;destination=-1; }
            case 4 -> { end=length+1;capacity=-1; }
            case 5 -> { capacity=-1;destination=-1; }
            case 6 -> { capacity=0; }
            case 7 -> { destination=-1; }
            case 8 -> { destination=Integer.MAX_VALUE; }
            case 9 -> { begin=2;end=1; }
            case 10 -> { begin=Integer.MIN_VALUE;end=0;capacity=0; }
            case 11 -> { end=Integer.MAX_VALUE; }
        }
        char[] output=capacity<0?null:new char[capacity];
        if(output!=null)for(int i=0;i<output.length;i++)output[i]='\u5a5a';
        try { input.getChars(begin,end,output,destination);return new String(output); }
        catch (StringIndexOutOfBoundsException error) { return "bounds:"+error.getMessage(); }
        catch (NullPointerException error) { return "npe"; }
    }
}
