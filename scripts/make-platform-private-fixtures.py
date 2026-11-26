"""Malformed-access callers, valid bytecode; never packaged as game inputs."""
import struct,sys
from pathlib import Path
u2=lambda n:struct.pack('>H',n)
u4=lambda n:struct.pack('>I',n)
def make(name,owner,method,desc,push,ret):
    cp=[]
    def utf(s):cp.append(b'\1'+u2(len(s))+s.encode());return len(cp)
    def cls(s):n=utf(s);cp.append(b'\7'+u2(n));return len(cp)
    this,parent,target=cls(name),cls('java/lang/Object'),cls(owner)
    target_name,target_desc=utf(method),utf(desc)
    cp.append(b'\x0c'+u2(target_name)+u2(target_desc));nt=len(cp)
    cp.append(b'\x0a'+u2(target)+u2(nt));ref=len(cp)
    run,signature,code_name=utf('run'),utf('()'+ret),utf('Code')
    body=push+b'\xb8'+u2(ref)+(b'\xad' if ret=='J' else b'\xb0' if ret.startswith(('L','[')) else b'\xb1')
    code=u2(3)+u2(0)+u4(len(body))+body+u2(0)+u2(0)
    return b'\xca\xfe\xba\xbe'+u2(0)+u2(65)+u2(len(cp)+1)+b''.join(cp)+u2(0x31)+u2(this)+u2(parent)+u2(0)+u2(0)+u2(1)+u2(9)+u2(run)+u2(signature)+u2(1)+u2(code_name)+u4(len(code))+code+u2(0)
root=Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True)
for name,owner,method,desc,push,ret in [
    ('PrivateHandle','jdk/internal/misc/Signal','handle0','(IJ)J',b'\x05\x09','J'),
    ('PrivateRaise','jdk/internal/misc/Signal','raise0','(I)V',b'\x05','V'),
    ('PrivateMode','sun/io/Win32ErrorMode','setErrorMode','(J)J',b'\x09','J'),
    ('PrivateLoaderRegister','java/lang/ClassLoader','registerNatives','()V',b'','V'),
    ('PrivateScopedRegister','jdk/internal/misc/ScopedMemoryAccess','registerNatives','()V',b'','V'),
    ('PrivateWinFsInit','java/io/WinNTFileSystem','initIDs','()V',b'','V'),
    ('PrivateReflectNew','java/lang/reflect/Array','newArray','(Ljava/lang/Class;I)Ljava/lang/Object;',b'\x01\x03','Ljava/lang/Object;'),
    ('PrivateReflectMulti','java/lang/reflect/Array','multiNewArray','(Ljava/lang/Class;[I)Ljava/lang/Object;',b'\x01\x01','Ljava/lang/Object;'),
]: (root/(name+'.class')).write_bytes(make('dev/boom/platform/'+name,owner,method,desc,push,ret))
