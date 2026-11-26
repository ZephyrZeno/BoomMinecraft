"""Literal fast-path inputs; general regex coverage is explicitly separate."""
import itertools, random, sys
from pathlib import Path
def units(s):
    return ','.join(f'{ord(c):x}' for c in s) or '-'
lines=[]
limits=[-2147483648,-3,-1,0,1,2,3,5,2147483647]
delimiters=[(',',','),('|',r'\|'),('.',r'\.'),('\\',r'\\'),('$',r'\$'),('?',r'\?'),('\x00','\x00'),('\n','\n'),('\uffff','\uffff'),('é','é'),('中',r'\中'),('_','_'),('] ','] ')]
delimiters=delimiters[:-1]+[(']',']'),('}', '}'),('(',r'\(')]
for ch,regex in delimiters:
    sources=['',ch,ch*2,'abc','a'+ch,'a'+ch*2+'b'+ch,ch+'a'+ch+'b',ch*3+'a'+ch*4,'\ud800'+ch+'\udc00'+ch+'\ud83d\ude00','\uffff'+ch+'\x00']
    sources += [''.join(c) for n in range(1,5) for c in itertools.product(['a',ch],repeat=n)]
    for source in sources:
        for mode in range(3):
            for limit in ([0] if mode==0 else limits):
                lines.append(f'{mode} {limit} {units(source)} {units(regex)}')
rng=random.Random(6301)
for _ in range(1200):
    ch,regex=rng.choice(delimiters);source=''.join(rng.choice(['a','b','\u0301','\ud800','\udc00',ch]) for _ in range(rng.randrange(80)))
    lines.append(f'{rng.randrange(3)} {rng.choice(limits)} {units(source)} {units(regex)}')
for mode in range(3):
    for source,regex in [('null','2c'),('61','null'),('null','null')]:lines.append(f'{mode} 0 {source} {regex}')
for cp in range(65536):
    lines.append(f'3 0 {units(chr(cp))} 2c')
    lines.append(f'3 0 0,20,{cp:x},20,1f 2c')
for source in ['-', 'null', '20,20,0,1f', 'd800,20,dc00', '20,d83d,de00,20', 'a0,20', '20,2003,20']:
    lines.append(f'3 0 {source} 2c')
Path(sys.argv[1]).write_text('\n'.join(lines)+'\n',encoding='ascii')
print(len(lines))
