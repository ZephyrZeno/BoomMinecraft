package dev.boom.strings;
public final class TextState {
    public static final String CONST="\u4e16\u754c\ud83d\ude80";
    public static String text=CONST;
    public static String alias=CONST;
    public static final String[] table={"","hello","A\0B",CONST,"\ud800x\udfff","Aa","BB","\u00ff\u0100\uffff"};
}
