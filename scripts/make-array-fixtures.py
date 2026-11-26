"""Generate rank-limit and malformed bytecode fixtures in the isolated test tree."""
import json
import struct
import sys
from pathlib import Path

root=Path(sys.argv[1])
root.mkdir(parents=True,exist_ok=True)
deep='new int'+'[1]'*254+'[0]'
empty='new int'+'[0]'*255
negative='new int'+'[0]'*254+'[-1]'
java=('package dev.boom.arrays; public final class DeepArray { '
      'public static Object deep(int v){return '+deep+';} '
      'public static int empty(int v){return ('+empty+').length;} '
      'public static int negative(int v){try{return ('+negative+').length;} '
      'catch(NegativeArraySizeException e){return 83;}}}')
(root/'DeepArray.java').write_text(java,encoding='utf-8')

u1=lambda n: struct.pack('>B',n)
u2=lambda n: struct.pack('>H',n)
u4=lambda n: struct.pack('>I',n)
def utf(s):
    b=s.encode('utf-8')
    return b'\x01'+u2(len(b))+b
cases=[]
for name,desc,dims in [('ZeroDimensions','[[I',0),('ExcessDimensions','[[I',3),
                       ('ScalarType','java/lang/Object',1),('ExcessRank','['*256+'I',1)]:
    binary='dev/boom/arrays/'+name
    cp=[utf(binary),b'\x07'+u2(1),utf('java/lang/Object'),b'\x07'+u2(3),
        utf('run'),utf('()Ljava/lang/Object;'),utf('Code'),utf(desc),b'\x07'+u2(8)]
    code=b'\x04'*dims+b'\xc5'+u2(9)+u1(dims)+b'\xb0'
    attr=u2(max(1,dims))+u2(0)+u4(len(code))+code+u2(0)+u2(0)
    data=(u4(0xcafebabe)+u2(0)+u2(65)+u2(len(cp)+1)+b''.join(cp)+
          u2(0x31)+u2(2)+u2(4)+u2(0)+u2(0)+u2(1)+u2(9)+u2(5)+u2(6)+u2(1)+u2(7)+u4(len(attr))+attr+u2(0))
    path=root/(name+'.class');path.write_bytes(data)
    cases.append(dict(name=binary,path=str(path.resolve()),descriptor=desc,dimensions=dims))
(root/'bad-arrays.json').write_text(json.dumps(cases,indent=2),encoding='utf-8')
