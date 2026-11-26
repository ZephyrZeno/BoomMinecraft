import dev.boom.fields.GetCharsProgram;
public final class GetCharsReference {
    public static void main(String[] args) {
        for(int mode=0;mode<48;mode++){
            String text=GetCharsProgram.run(mode);StringBuilder encoded=new StringBuilder();
            for(char c:text.toCharArray())encoded.append(String.format("%02x%02x",c&255,c>>>8));
            System.out.println(encoded);
        }
    }
}
