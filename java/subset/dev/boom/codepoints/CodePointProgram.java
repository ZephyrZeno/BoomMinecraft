package dev.boom.codepoints;
public final class CodePointProgram {
 public static int run(int first,int second,int index,int nullable) {
  try {String value=nullable!=0?null:new String(new char[]{(char)first,(char)second});return value.codePointAt(index);}
  catch(StringIndexOutOfBoundsException error){return -2;}
  catch(NullPointerException error){return -1;}
 }
}
