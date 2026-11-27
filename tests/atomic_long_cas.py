"""Source/native boundaries and actual machine tampering, not guest startup."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import subprocess
from types import SimpleNamespace
import unittest
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]

def module(name):
    spec=importlib.util.spec_from_file_location('atomic_unit_'+name,ROOT/'scripts'/(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

B=module('atomic-long-cas-candidate');C=B.C;S=B.S;I=module('verify-translation-ir')

def fixture(*,access=0x10a,major=65,native_code=False,field_name='VM_SUPPORTS_LONG_CAS',call=True):
    def utf(text):
        raw=text.encode();return b'\x01'+struct.pack('>H',len(raw))+raw
    cp=[utf(C.OWNER),b'\x07\0\x01',utf('java/lang/Object'),b'\x07\0\x03',utf('VMSupportsCS8'),utf('()Z'),
        utf('<clinit>'),utf('()V'),utf('Code'),utf(field_name),utf('Z'),b'\x0c\0\x05\0\x06',
        b'\x0a\0\x02\0\x0c',b'\x0c\0\x0a\0\x0b',b'\x09\0\x02\0\x0e']
    def code(data):
        body=struct.pack('>HHI',1,0,len(data))+data+b'\0\0\0\0'
        return struct.pack('>HI',9,len(body))+body
    field=struct.pack('>4H',0x18,10,11,0)
    native=struct.pack('>4H',access,5,6,int(native_code))+(code(b'\x04\xac') if native_code else b'')
    bytecode=(b'\xb8\0\x0d' if call else b'\x04')+b'\xb3\0\x0f\xb1'
    initializer=struct.pack('>4H',8,7,8,1)+code(bytecode)
    return struct.pack('>IHHH',0xcafebabe,0,major,len(cp)+1)+b''.join(cp)+struct.pack('>5H',0x21,2,4,0,1)+field+\
        struct.pack('>H',2)+native+initializer+b'\0\0'

def model(raw,*,generated=False,source_id='jdk:java.base',ids=(1700,1701)):
    owner=dict(id=0,name=C.OWNER,origin=dict(loader='bootstrap',source_id=source_id,generated=generated,
        sha256=hashlib.sha256(raw).hexdigest()),method_ids=list(ids))
    fake=SimpleNamespace(module=lambda name,file:I,check=S.check,original_class=lambda summary,cls:raw,ART=S.ART,artifact=S.artifact)
    return C.index({},[owner],fake)


class OriginalSource(unittest.TestCase):
    def test_dynamic_IDs_preserve_original_call_and_publication(self):
        meta=model(fixture(),ids=(9011,9012))
        self.assertEqual(meta['methods'][0]['method'],9011);self.assertEqual(meta['methods'][0]['access'],0x10a)
        self.assertEqual(meta['original_java'][0]['method'],9012)
        self.assertEqual(meta['original_java'][0]['publication']['native_call_pc'],0)
        self.assertEqual(meta['original_java'][0]['publication']['source_putstatic_pc'],3)
        self.assertEqual(meta['capability_field']['symbol'],'boom_s0_0')
        self.assertEqual(meta['native_root_spans'],[]);self.assertEqual(meta['required_java_methods'],[])

    def test_nonstatic_or_nonprivate_or_Java_Code_native_rejected(self):
        for args in ({'access':0x102},{'access':0x109},{'native_code':True}):
            with self.subTest(args=args),self.assertRaises(ValueError):model(fixture(**args))

    def test_missing_original_publication_or_wrong_version_rejected(self):
        for args in ({'major':61},{'field_name':'host_patched_capability'},{'call':False}):
            with self.subTest(args=args),self.assertRaises(ValueError):model(fixture(**args))

    def test_generated_or_foreign_source_cannot_bind_JDK_native(self):
        for args in ({'generated':True},{'source_id':'fixture:untrusted'}):
            with self.subTest(args=args),self.assertRaises(ValueError):model(fixture(),**args)


@unittest.skipUnless(B.ASSEMBLER.is_file(),'Actual ml64 required')
class NativeMachine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output=S.ART/'atomic-long-cas/unit-machines'/uuid4().hex;cls.output.mkdir(parents=True)
        cls.text='option casemap:none\n'+C.data(None)+B.KERNEL.read_text()+'\nEND\n'
        cls.source,cls.obj=cls.output/'kernel.asm',cls.output/'kernel.obj';cls.source.write_text(cls.text)
        subprocess.run([str(B.ASSEMBLER),'/nologo','/c','/Fo'+str(cls.obj),str(cls.source)],check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        cls.raw=cls.obj.read_bytes();cls.normal=B.O.normalized_coff(cls.obj)

    def test_actual_unwind_records_the_RBX_push(self):
        count=struct.unpack_from('<H',self.raw,2)[0]
        for i in range(count):
            header=20+40*i
            if self.raw[header:header+8].rstrip(b'\0')==b'.xdata':
                size,at=struct.unpack_from('<II',self.raw,header+16);info=self.raw[at:at+size]
                self.assertEqual(info[:6],bytes([1,1,1,0,1,0x30]));break
        else:self.fail('Missing actual x64 unwind')
        self.assertEqual(self.normal['imports'],[])

    def test_instruction_mutation_is_detected_by_canonical_reassembly(self):
        raw=bytearray(self.raw);at=raw.index(b'\x0f\xa2');raw[at:at+2]=b'\x90\x90'
        p=self.output/'no-CPUID.obj';p.write_bytes(raw)
        self.assertNotEqual(B.O.normalized_coff(p),self.normal)
        with self.assertRaisesRegex(ValueError,'Canonical code/data/flags'):B.machine(self.text,p,B.ASSEMBLER)

    def test_section_flags_and_unwind_changes_do_not_hide_behind_symbols(self):
        sections={};count=struct.unpack_from('<H',self.raw,2)[0]
        for i in range(count):
            at=20+i*40;sections[self.raw[at:at+8].rstrip(b'\0').decode()]=at
        text=sections['.text' if '.text' in sections else '.text$mn']
        raw=bytearray(self.raw);flags=struct.unpack_from('<I',raw,text+36)[0];struct.pack_into('<I',raw,text+36,flags^0x80000000)
        p=self.output/'bad-flags.obj';p.write_bytes(raw);self.assertNotEqual(B.O.normalized_coff(p),self.normal)
        raw=bytearray(self.raw);at=struct.unpack_from('<I',raw,sections['.xdata']+20)[0];raw[at+5]^=0x10
        p=self.output/'bad-unwind.obj';p.write_bytes(raw);self.assertNotEqual(B.O.normalized_coff(p),self.normal)


if __name__=='__main__':unittest.main()
