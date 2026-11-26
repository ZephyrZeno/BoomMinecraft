// Locked JVM native cache oracle. No file mutation or game execution.
public final class WindowsFileSystemReference {
    public static void main(String[] args) throws Exception {
        Class<?> type=Class.forName("java.io.WinNTFileSystem");
        var init=type.getDeclaredMethod("initIDs");init.setAccessible(true);
        for(int i=0;i<256;i++)init.invoke(null);
        var path=java.io.File.class.getDeclaredField("path");
        if(path.getType()!=String.class||path.getModifiers()!=0x12)throw new AssertionError("File.path declaration");
        System.out.println("init_calls=256;private_final_String_path=1");
    }
}
