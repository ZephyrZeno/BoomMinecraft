"""Remove only the NestMembers attribute of the isolated descriptor test host."""
import struct
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = path.read_bytes()
pos = 8

def u2():
    global pos
    value = struct.unpack_from(">H", data, pos)[0]
    pos += 2
    return value

def u4():
    global pos
    value = struct.unpack_from(">I", data, pos)[0]
    pos += 4
    return value

cp = {}
count = u2()
i = 1
while i < count:
    tag = data[pos]
    pos += 1
    if tag == 1:
        size = u2()
        cp[i] = data[pos:pos + size].decode("utf-8")
        pos += size
    elif tag in (7, 8, 16, 19, 20):
        cp[i] = u2()
    elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
        pos += 4
    elif tag in (5, 6):
        pos += 8
        i += 1
    elif tag == 15:
        pos += 3
    else:
        raise ValueError(f"Unknown test constant {tag}")
    i += 1
u2()
assert cp[cp[u2()]] == "dev/boom/descriptors/DescriptorEntry"
u2()
interfaces = u2()
pos += interfaces * 2
for _ in range(2):
    for _ in range(u2()):
        pos += 6
        for _ in range(u2()):
            u2()
            size = u4()
            pos += size
start = pos
attrs = []
removed = 0
for _ in range(u2()):
    begin = pos
    name = cp[u2()]
    size = u4()
    pos += size
    if name == "NestMembers":
        removed += 1
    else:
        attrs.append(data[begin:pos])
assert pos == len(data) and removed == 1
path.write_bytes(data[:start] + struct.pack(">H", len(attrs)) + b"".join(attrs))
