package dev.boom.resources;
import java.io.InputStream;

public final class ResourceEntry {
    static String name(int n) { return switch(n) {
        case 0 -> "/version.json";
        case 1 -> "local.txt";
        case 2 -> "/shared.txt";
        case 3 -> "/empty.bin";
        case 4 -> "/missing.bin";
        case 5 -> "/unicode/\ud83d\ude00.txt";
        case 6 -> "/unicode/\ue000.txt";
        case 7 -> "/release.txt";
        case 8 -> "/META-INF/versions/9/release.txt";
        case 9 -> "String.class";
        case 10 -> "/java/lang/Object.class";
        case 11 -> "/jdk/internal/misc/Unsafe.class";
        case 12 -> "/java/lang/uniName.dat";
        case 13 -> "/dev/boom/resources/Dormant.class";
        case 14 -> "/empty-dir/";
        case 15 -> "/shared.txt\0";
        case 16 -> "/unicode/\ud800.txt";
        case -1 -> null;
        default -> "/absent-" + n;
    }; }
    static Class<?> anchor(int n) { return switch(n) {
        case 0 -> ResourceEntry.class;
        case 1 -> String.class;
        case 2 -> String[].class;
        case 3 -> int[].class;
        case 4 -> int[].class.getComponentType();
        case 5 -> Dormant.class;
        case -1 -> null;
        default -> Marker.class;
    }; }
    public static int run(int n, int a, int operation) throws Exception {
        Class<?> c=anchor(a); String name=name(n);
        InputStream s=c.getResourceAsStream(name);
        if(s==null)return -777;
        if(operation==1){int count=s.available();s.close();return count;}
        if(operation==2){InputStream other=c.getResourceAsStream(name);int first=s.read(),second=other.read();s.close();other.close();return first==second?first:-999;}
        int hash=0;for(int b;(b=s.read())!=-1;)hash=hash*31+b;
        s.close();return hash+State.initialized*1009;
    }
}
interface Marker {}
final class State { static int initialized; }
final class Dormant { static { State.initialized++; } }
