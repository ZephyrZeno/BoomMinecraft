"""Valid classfiles that attempt private System native/bootstrap calls."""
import json,struct,sys
from pathlib import Path
root=Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True)
u2=lambda v:struct.pack('>H',v)
u4=lambda v:struct.pack('>I',v)
def utf(s):
    b=s.encode('utf-8');return b'\x01'+u2(len(b))+b
cases=[]
for name,desc in [('setIn0','(Ljava/io/InputStream;)V'),('setOut0','(Ljava/io/PrintStream;)V'),('setErr0','(Ljava/io/PrintStream;)V'),('initPhase1','()V')]:
    binary='dev/boom/system/Bad_'+name
    cp=[utf(binary),b'\x07'+u2(1),utf('java/lang/Object'),b'\x07'+u2(3),utf('run'),utf('()V'),utf('Code'),utf('java/lang/System'),b'\x07'+u2(8),utf(name),utf(desc),b'\x0c'+u2(10)+u2(11),b'\x0a'+u2(9)+u2(12)]
    code=(b'' if name=='initPhase1' else b'\x01')+b'\xb8'+u2(13)+b'\xb1'
    attr=u2(1)+u2(0)+u4(len(code))+code+u2(0)+u2(0)
    data=u4(0xcafebabe)+u2(0)+u2(65)+u2(len(cp)+1)+b''.join(cp)+u2(0x31)+u2(2)+u2(4)+u2(0)+u2(0)+u2(1)+u2(9)+u2(5)+u2(6)+u2(1)+u2(7)+u4(len(attr))+attr+u2(0)
    p=root/Path(binary+'.class');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    cases.append(dict(name=binary,path=str(p.resolve()),method=name))
(root/'bad-system-streams.json').write_text(json.dumps(cases,indent=2),encoding='utf-8')
