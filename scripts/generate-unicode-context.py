"""Build-only Unicode context table for the locked Java 21 case algorithm."""
import argparse, hashlib, json
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--unicode-data',type=Path,required=True)
parser.add_argument('--jdk-base',type=Path,required=True)
args=parser.parse_args()
raw=args.unicode_data.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='806e9aed65037197f1ec85e12be6e8cd870fc5608b4de0fffd990f689f376a73'
values=[0]*0x110000
first=None
for line in raw.decode('utf-8').splitlines():
    fields=line.split(';');cp=int(fields[0],16);prop=int(fields[3])|(256 if fields[2] in ('Lu','Ll','Lt') else 0)
    if fields[1].endswith(', First>'):first=(cp,prop)
    elif fields[1].endswith(', Last>'):
        assert first is not None and first[1]==prop
        values[first[0]:cp+1]=[prop]*(cp-first[0]+1);first=None
    else:values[cp]=prop
assert first is None
# ConditionalSpecialCasing.isCased has this explicit compatibility list.
for begin,end in [(0x2b0,0x2b8),(0x2c0,0x2c1),(0x2e0,0x2e4),(0x345,0x345),
                  (0x37a,0x37a),(0x1d2c,0x1d61),(0x2160,0x217f),(0x24b6,0x24e9)]:
    for cp in range(begin,end+1):values[cp]|=256
rows=[];start=0
for end in range(1,len(values)+1):
    if end==len(values) or values[end]!=values[start]:
        if values[start]:rows.append((start,end-1,values[start]))
        start=end
manifest=json.loads(args.jdk_base.read_text(encoding='utf-8-sig'))
names=['java.lang.ConditionalSpecialCasing','java.lang.StringUTF16','sun.text.RuleBasedBreakIterator',
       'sun.text.CompactByteArray','sun.text.SupplementaryCharacterData']
data=dict(abi=1,unicode_version='15.0.0',source_sha256=hashlib.sha256(raw).hexdigest(),
          sigma_cased_profile='Java21-ConditionalSpecialCasing-type-and-compatibility-ranges',
          rows=len(rows),codewords_sha256=hashlib.sha256(b''.join(v.to_bytes(2,'little') for v in values)).hexdigest(),
          row_bytes_sha256=hashlib.sha256(b''.join(v.to_bytes(4,'little') for row in rows for v in row)).hexdigest(),
          jdk_sources={name:manifest['classes'][name]['sha256'] for name in names})
asm=Path('native/runtime/unicode_context.asm');source=asm.read_text()
begin='; BEGIN GENERATED UNICODE CONTEXT DATA';end='; END GENERATED UNICODE CONTEXT DATA'
head,tail=source.split(begin,1);_,tail=tail.split(end,1)
body='\n.const\nunicode_context_count EQU '+str(len(rows))+'\nALIGN 4\nunicode_context_rows LABEL DWORD\n'
body+=''.join('    DWORD '+', '.join('0%08Xh'%v for v in row)+'\n' for row in rows)
asm.write_text(head+begin+body+end+tail)
Path('native/runtime/unicode_context.json').write_text(json.dumps(data,indent=2)+'\n')
print(json.dumps(dict(rows=len(rows),codewords_sha256=data['codewords_sha256'])))
