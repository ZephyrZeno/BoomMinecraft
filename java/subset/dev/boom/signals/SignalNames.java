package dev.boom.signals;
// String producers for raw VM service verification; they never invoke Signal Java APIs.
public final class SignalNames {
    public static String literal(int n){String s=switch(n&31){
        case 0->"ABRT";case 1->"FPE";case 2->"SEGV";case 3->"INT";case 4->"TERM";case 5->"BREAK";case 6->"ILL";
        case 7->"";case 8->"HUP";case 9->"SIGINT";case 10->"int";case 11->"INT\0";case 12->"\0INT";
        case 13->"IN\u0100";case 14->"TERM ";case 15->"BREAK\0X";case 16->"ABRT\ud800";case 17->"\ud800";
        case 18->"\ud83e\uddf1";case 19->"0";case 20->"TERM\0more";case 21->"ILL\udfff";case 22->"ＦＰＥ";
        case 23->"ABRT\1";case 24->"İNT";case 25->"break";case 26->"SIGABRT_COMPAT";case 27->"\0";
        case 28->"00000000";case 29->"SEGV\n";case 30->"FPE\ud800\udc00";default->null;
    };if(s!=null)s.startsWith("",-1);return s;}
    public static String raw(int packed){char c=(char)packed;String s=switch((packed>>>16)&7){
        case 0->""+c;case 1->"I"+c+"T";case 2->"ABR"+c;case 3->"BR"+c+"AK";
        case 4->"TER"+c;case 5->"FP"+c;case 6->"SE"+c+"V";default->"IL"+c;
    };s.startsWith("",-1);return s;}
}
