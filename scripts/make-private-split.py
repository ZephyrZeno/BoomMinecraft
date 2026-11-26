"""Valid JVM bytecode making an illegal private String.split call."""
import struct,sys
from pathlib import Path
u2=lambda n:struct.pack('>H',n)
u4=lambda n:struct.pack('>I',n)
def utf(s):
    b=s.encode();return b'\1'+u2(len(b))+b
cp=[utf('dev/boom/split/PrivateSplit'),b'\7'+u2(1),utf('java/lang/Object'),b'\7'+u2(3),utf('main'),utf('([Ljava/lang/String;)V'),utf('Code'),utf('java/lang/String'),b'\7'+u2(8),utf('split'),utf('(Ljava/lang/String;IZ)[Ljava/lang/String;'),b'\x0c'+u2(10)+u2(11),b'\x0a'+u2(9)+u2(12)]
body=b'\x01\x01\x03\x03\xb6'+u2(13)+b'\x57\xb1'
code=u2(4)+u2(1)+u4(len(body))+body+u2(0)+u2(0)
raw=u4(0xcafebabe)+u2(0)+u2(65)+u2(len(cp)+1)+b''.join(cp)+u2(0x31)+u2(2)+u2(4)+u2(0)+u2(0)+u2(1)+u2(9)+u2(5)+u2(6)+u2(1)+u2(7)+u4(len(code))+code+u2(0)
p=Path(sys.argv[1])/'dev/boom/split/PrivateSplit.class';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
