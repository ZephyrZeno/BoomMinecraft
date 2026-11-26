"""Reject validly encoded record sites with mismatched names or setter handles."""
import json,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1]);boom=Path(sys.argv[2]).resolve();base=Path(sys.argv[3]).resolve()
program=json.loads((root/'program/program.json').read_text(encoding='utf-8-sig'))
site=next(b for b in program['record_sites'] if b['plan']['host'].endswith('$Point'))
source=root/'classes/dev/boom/records/RecordProgram$Point.class';raw=source.read_bytes()
names=b'x;y;yes;ch;name';assert raw.count(names)==1
changed=bytearray(raw);position=raw.index(names);changed[position]=ord('q')
variants={'names':bytes(changed)}
count=int.from_bytes(raw[8:10],'big');at=10;index=1;handles={}
while index<count:
 tag=raw[at];at+=1
 if tag==1:at+=2+int.from_bytes(raw[at:at+2],'big')
 elif tag in (7,8,16,19,20):at+=2
 elif tag in (9,10,11,12,17,18,3,4):at+=4
 elif tag in (5,6):at+=8;index+=1
 elif tag==15:handles[index]=at;at+=3
 else:raise AssertionError(tag)
 index+=1
getter=next(offset for offset in handles.values() if raw[offset]==1)
changed=bytearray(raw);changed[getter]=3;variants['setter']=bytes(changed)
for name,data in variants.items():
 case=root/'negative'/name;case.mkdir(parents=True,exist_ok=True);bad=case/source.name;bad.write_bytes(data);output=case/'output'
 command=[str(boom),'compile-program','--metadata-lock','.boom/locks/server.json','--jdk-base',str(base),'--entry-class','dev/boom/records/RecordProgram','--method','run','--descriptor','(I)Ljava/lang/String;','--output',str(output),'--assemble']
 for original in sorted((root/'classes/dev/boom/records').glob('*.class')):command+=['--class-file',str(bad if original==source else original)]
 result=subprocess.run(command,capture_output=True,timeout=60);(case/'compile.err').write_bytes(result.stderr)
 assert result.returncode!=0 and not (output/'program.json').exists() and b'Record bootstrap' in result.stderr,(name,result.stderr.decode(errors='replace'))
print(json.dumps(dict(passed=True,rejected_shapes=list(variants),output_programs_written=0)))
