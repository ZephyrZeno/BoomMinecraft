"""A valid classfile attempting an illegal private Signal native call."""
import struct,sys
from pathlib import Path
u2=lambda v:struct.pack('>H',v)
u4=lambda v:struct.pack('>I',v)
def utf(s):
    b=s.encode();return b'\x01'+u2(len(b))+b
name='dev/boom/signals/BadLookup'
cp=[utf(name),b'\x07'+u2(1),utf('java/lang/Object'),b'\x07'+u2(3),utf('run'),utf('()I'),utf('Code'),utf('jdk/internal/misc/Signal'),b'\x07'+u2(8),utf('findSignal0'),utf('(Ljava/lang/String;)I'),b'\x0c'+u2(10)+u2(11),b'\x0a'+u2(9)+u2(12)]
code=b'\x01\xb8'+u2(13)+b'\xac';attr=u2(1)+u2(0)+u4(len(code))+code+u2(0)+u2(0)
data=u4(0xcafebabe)+u2(0)+u2(65)+u2(len(cp)+1)+b''.join(cp)+u2(0x31)+u2(2)+u2(4)+u2(0)+u2(0)+u2(1)+u2(9)+u2(5)+u2(6)+u2(1)+u2(7)+u4(len(attr))+attr+u2(0)
p=Path(sys.argv[1])/Path(name+'.class');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
