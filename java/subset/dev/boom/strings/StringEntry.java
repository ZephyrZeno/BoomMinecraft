package dev.boom.strings;
public final class StringEntry {
    public static int length(int which) {return TextA.pick(which).length();}
    public static int empty(int which) {return TextA.pick(which).isEmpty()?1:0;}
    public static int character(int which,int index) {return TextA.pick(which).charAt(index);}
    public static int hash(int which) {return TextA.pick(which).hashCode();}
    public static int equal(int a,int b) {return TextA.pick(a).equals(TextB.pick(b))?1:0;}
    public static int compare(int a,int b) {return TextA.pick(a).compareTo(TextB.pick(b));}
    public static int identity(int which) {return TextA.pick(which)==TextB.pick(which)?1:0;}
    public static int intern(int which) {return TextA.pick(which).intern()==TextB.pick(which)?1:0;}
    public static int toStringIdentity(int which) {return TextA.pick(which).toString()==TextB.pick(which)?1:0;}
    public static int notString(int which) {return TextA.pick(which).equals(new int[3])?1:0;}
    public static int equalsNull(int which) {return TextA.pick(which).equals(null)?1:0;}
    public static int nullReceiver(int which) {String text=which<0?null:TextA.pick(which);return text.length();}
    public static int nullCharacter(int which,int index) {String text=which<0?null:TextA.pick(which);return text.charAt(index);}
    public static int nullOther(int which) {return TextA.pick(which).compareTo(null);}
    public static int array(int count,int index) {String[] strings=new String[count];for(int i=0;i<count;i++)strings[i]=TextA.pick(i);return strings[index].hashCode();}
    public static int nullElement(int count,int index) {String[] strings=new String[count];return strings[index].length();}
    public static int state(int which) {return TextState.table[which&7].hashCode()^TextState.text.length()^TextState.alias.length();}
    public static int hashMix(int a,int b) {return "hello".hashCode()^a^b;}
    public static int failure() {return TextFailure.value;}
    public static int unsupportedConstructor() {return new String("hello").length();}
    public static int unsupportedMethod() {return "hello".toUpperCase().length();}
}
