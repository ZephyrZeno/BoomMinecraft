"""Normal-layout concat kernel cases; no claim of source bootstrap execution."""
import argparse
import random
import struct
from pathlib import Path


def units(s):
    raw=s.encode('utf-16-le',errors='surrogatepass')
    return list(struct.unpack('<'+'H'*(len(raw)//2),raw))


def prepare(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True);cases=[]
    ints=[0,1,-1,127,128,255,256,-128,-32768,32767,-2147483648,2147483647]
    longs=[0,1,-1,-9223372036854775808,9223372036854775807,4294967296,-4294967296]
    def case(args,fragments=None):
        parts=[]
        if fragments is None:fragments=[units('prefix\0\ud800[')]+[units('|')]*(len(args)-1)+[units(']\udc00')]
        for i in range(len(args)+1):
            if fragments[i]:parts.append((0,0,fragments[i]))
            if i<len(args):parts.append((args[i][0],i,[]))
        cases.append((args,parts))
    cases.append(([],[]))
    case([], [units('literal\0\ud83d\ude00')])
    for i in ints:
        for j in longs:case([(1,i,None),(2,j,None)])
    for value in [[],units('latin\xff'),units('汉字\U0001f600'),[0,0xd800,65,0xdc00],None]:
        for wide in (0,1):
            case([(5,wide,value)])
    for value in [0,1,255,256,0x4e2d,0xd800,0xdc00,0xffff]:case([(4,value,None),(3,value&1,None)])
    rng=random.Random(98)
    for _ in range(512):
        args=[]
        for i in range(rng.randrange(1,12)):
            kind=rng.randrange(1,6)
            value= rng.getrandbits(64) if kind==2 else rng.getrandbits(32) if kind==1 else rng.randrange(2) if kind==3 else rng.randrange(65536) if kind==4 else rng.randrange(2)
            text=([rng.randrange(65536) for _ in range(rng.randrange(12))] if rng.randrange(8) else None) if kind==5 else None
            args.append((kind,value,text))
        case(args)
    case([(5,0,[97]*70001)])
    case([(5,1,[0x4e2d]*70001)])
    case([(2,-9223372036854775808,None)]*100,[[]]*101)
    with (output/'cases.bin').open('wb') as f:
        def i(v):f.write(struct.pack('<i',v))
        def text(t):
            i(-1 if t is None else len(t))
            if t:f.write(struct.pack('<'+'H'*len(t),*t))
        i(0x4a434f4e);i(len(cases))
        for args,parts in cases:
            i(len(args))
            for kind,bits,t in args:i(kind);f.write(struct.pack('<Q',bits&0xffffffffffffffff));text(t)
            i(len(parts))
            for kind,index,t in parts:i(kind);i(index);text(t)
    return len(cases)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print('Prepared concat cases='+str(prepare(a.output)))
