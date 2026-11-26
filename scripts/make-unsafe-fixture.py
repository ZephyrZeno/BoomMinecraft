"""Application access to the private Unsafe registrar must fail."""
import struct
import sys
from pathlib import Path
u2 = lambda n: struct.pack('>H', n)
u4 = lambda n: struct.pack('>I', n)
def utf(text):
    data = text.encode()
    return b'\1' + u2(len(data)) + data
name = 'dev/boom/unsafe/BadRegistration'
cp = [utf(name), b'\7'+u2(1), utf('java/lang/Object'), b'\7'+u2(3), utf('run'), utf('()V'), utf('Code'), utf('jdk/internal/misc/Unsafe'), b'\7'+u2(8), utf('registerNatives'), b'\x0c'+u2(10)+u2(6), b'\x0a'+u2(9)+u2(11)]
code = u2(0)+u2(0)+u4(4)+b'\xb8\0\x0c\xb1'+u2(0)+u2(0)
method = u2(9)+u2(5)+u2(6)+u2(1)+u2(7)+u4(len(code))+code
data = b'\xca\xfe\xba\xbe'+u2(0)+u2(65)+u2(13)+b''.join(cp)+u2(0x31)+u2(2)+u2(4)+u2(0)+u2(0)+u2(1)+method+u2(0)
path = Path(sys.argv[1])/(name+'.class')
path.parent.mkdir(parents=True, exist_ok=True)
path.write_bytes(data)
