package dev.boom.join;

public final class JoinEntry {
    @SuppressWarnings("unchecked")
    public static int run(int mode,int count,int delimiter,int behavior) {
        if(mode==-1) return State.trace;
        State.trace=0;
        CharSequence sep=switch(delimiter) {
            case 0 -> "-";
            case 1 -> "";
            case 2 -> "中文😀";
            case 3 -> "\0\ud800";
            case 4 -> null;
            case 5 -> new Sequence("/",-2,0);
            case 6 -> new Sequence(null,-2,0);
            default -> new Sequence("/",-2,1);
        };
        String result;
        if(mode==0 || mode==4) {
            String[] values=mode==4?null:new String[count];
            if(values!=null) for(int i=0;i<count;i++) values[i]=text(i);
            result=String.join(sep,values);
        } else if(mode==1) {
            CharSequence[] values=new CharSequence[count];
            for(int i=0;i<count;i++) values[i]=(i%4==3)?null:new Sequence((behavior==2&&i==1)?null:text(i)==null?"fallback":text(i),i,(behavior==1&&i==1)?1:0);
            result=String.join(sep,values);
        } else if(mode==3) {
            result=String.join(sep,(Iterable<CharSequence>)(Iterable<?>)new RawItems(count));
        } else {
            result=String.join(sep,mode==5?null:new Items(count,behavior));
        }
        return result.hashCode()*31+State.trace;
    }
    static String text(int i) {
        return switch(i%5) {case 0->"alpha";case 1->"中😀";case 2->"\0\ud800";case 3->null;default->"";};
    }
    public static int identity(int n) {
        String first="single";
        String[] values=n==0?new String[0]:new String[]{first};
        String result=String.join("",values);
        return (result==first?1:0)|(result==""?2:0)|(result.intern()==(n==0?"":first)?4:0);
    }
    public static int parallel(int n) {
        return String.join("::",new Range(n&31)).hashCode();
    }
    public static int budget(int count) {return String.join("::",new Range(count)).hashCode();}
    public static int bridge(int n) {
        CharSequence c=(n&1)==0?"a😀":new Sequence("a😀",0,0);
        return c.length()*31+c.charAt(n>>1)+c.toString().hashCode();
    }
    public static int unsupported(int n) {return String.format("%d",n).length();}
}
final class State {static int trace;static void add(int n){trace=trace*31+n;}}
final class Sequence implements CharSequence {
    final String text;final int id,fail;
    Sequence(String text,int id,int fail){this.text=text;this.id=id;this.fail=fail;}
    public int length(){return text.length();}
    public char charAt(int index){return text.charAt(index);}
    public CharSequence subSequence(int start,int end){return text.subSequence(start,end);}
    public synchronized String toString(){State.add(100+id);if(fail!=0){int[] bad=new int[-1];return ""+bad.length;}return text;}
}
final class Items implements Iterable<CharSequence> {
    final int count,behavior;
    Items(int count,int behavior){this.count=count;this.behavior=behavior;}
    public java.util.Iterator<CharSequence> iterator(){State.add(1);return behavior==4?null:new Cursor(count,behavior);}
}
final class Cursor implements java.util.Iterator<CharSequence> {
    final int count,behavior;int index;
    Cursor(int count,int behavior){this.count=count;this.behavior=behavior;}
    public boolean hasNext(){State.add(2);if(behavior==5&&index==1){int[] bad=new int[-1];return bad.length!=0;}return index<count;}
    public CharSequence next(){State.add(3);int i=index++;if(behavior==3&&i==1){int[] bad=new int[-1];return ""+bad.length;}return i%4==3?null:new Sequence((behavior==2&&i==1)?null:JoinEntry.text(i)==null?"fallback":JoinEntry.text(i),i,(behavior==1&&i==1)?1:0);}
}
final class Range implements Iterable<CharSequence> {
    final int count;Range(int count){this.count=count;}
    public java.util.Iterator<CharSequence> iterator(){return new RangeCursor(count);}
}
final class RangeCursor implements java.util.Iterator<CharSequence> {
    final int count;int index;RangeCursor(int count){this.count=count;}
    public boolean hasNext(){return index<count;}
    public CharSequence next(){index++;return "x";}
}
final class RawItems implements Iterable<Object> {
    final int count;RawItems(int count){this.count=count;}
    public java.util.Iterator<Object> iterator(){return new RawCursor(count);}
}
final class RawCursor implements java.util.Iterator<Object> {
    final int count;int index;RawCursor(int count){this.count=count;}
    public boolean hasNext(){State.add(2);return index<count;}
    public Object next(){State.add(3);return index++==1?new Object():"valid";}
}
