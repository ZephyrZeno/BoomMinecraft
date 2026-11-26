package dev.boom.subset;
import com.mojang.brigadier.context.StringRange;

/** Compiler fixture calling the unchanged, locked Minecraft dependency. */
public final class RangeProgramEntry {
    public static int length(int start,int end) {return StringRange.between(start,end).getLength();}
    public static int start(int value) {return StringRange.at(value).getStart();}
}
