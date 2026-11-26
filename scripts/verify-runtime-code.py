"""Compare tested and packaged PE code/storage/unwind sections, excluding timestamps."""
import hashlib
import json
import struct
import sys
from pathlib import Path

def sections(path):
    data=Path(path).read_bytes()
    assert data[:2]==b'MZ'
    pe=struct.unpack_from('<I',data,0x3c)[0]
    assert data[pe:pe+4]==b'PE\0\0'
    machine,count=struct.unpack_from('<HH',data,pe+4)
    size=struct.unpack_from('<H',data,pe+20)[0]
    assert machine==0x8664 and struct.unpack_from('<H',data,pe+24)[0]==0x20b
    result={}
    for i in range(count):
        at=pe+24+size+i*40
        name=data[at:at+8].rstrip(b'\0').decode('ascii')
        length,offset=struct.unpack_from('<II',data,at+16)
        block=data[offset:offset+length]
        assert len(block)==length
        result[name]=hashlib.sha256(block).hexdigest()
    assert all(name in result for name in ('.text','.data','.pdata'))
    return result

a,b=sections(sys.argv[1]),sections(sys.argv[2])
names=('.text','.data','.pdata')
assert all(a[name]==b[name] for name in names),'Tested and packaged runtime code/storage/unwind differ'
print(json.dumps(dict(passed=True,matching_sections={name:a[name] for name in names},
                      full_PE_byte_equality_claimed=False)))
