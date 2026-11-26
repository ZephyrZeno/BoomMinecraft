"""Method descriptor and classfile-attribute boundary checks, no guest claims."""
import importlib.util
from pathlib import Path
import struct
import subprocess
import unittest
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('normal_methods_source_test',ROOT/'scripts/normal-methods-source.py')
N=importlib.util.module_from_spec(spec);spec.loader.exec_module(N)


def classfile(*,attributes=(),descriptor='()V',flags=0x1041,exception_index=None):
    """A labelled parser fixture, never registered as an original guest class."""
    cp=[]
    def utf(text):
        raw=text.encode();cp.append(b'\1'+struct.pack('>H',len(raw))+raw);return len(cp)
    def cls(name):
        i=utf(name);cp.append(b'\7'+struct.pack('>H',i));return len(cp)
    owner=cls('ParserFixture');base=cls('java/lang/Object');name=utf('bridge')
    desc=utf(descriptor);attrs=[]
    for key,value in attributes:
        key_index=utf(key)
        if key=='Signature':value=struct.pack('>H',utf(value))
        attrs.append(struct.pack('>HI',key_index,len(value))+value)
    if exception_index is not None:
        key=utf('Exceptions');value=struct.pack('>HH',1,exception_index)
        attrs.append(struct.pack('>HI',key,len(value))+value)
    return b'\xca\xfe\xba\xbe\0\0\0A'+struct.pack('>H',len(cp)+1)+b''.join(cp)+\
        struct.pack('>HHHHHH',0x21,owner,base,0,0,1)+struct.pack('>HHHH',flags,name,desc,len(attrs))+b''.join(attrs)+b'\0\0'


class MethodSourceContract(unittest.TestCase):
    def test_reference_array_primitive_and_void_descriptor(self):
        self.assertEqual(N.descriptor_types('(I[[Ljava/lang/String;[DJ)Ljava/lang/Object;'),
            (['I','[[Ljava/lang/String;','[D','J'],'Ljava/lang/Object;'))
        self.assertEqual(N.descriptor_types('()V'),([], 'V'))

    def test_descriptor_rejects_void_parameters_and_trailing_or_truncated_types(self):
        for value in ('','V','(V)V','([V)V','([)V','(L;)V','(Ljava/lang/Object)V','()','()VV','()Ljava/lang/X;garbage'):
            with self.subTest(value=value),self.assertRaises(ValueError):N.descriptor_types(value)

    def test_empty_and_absent_attributes_are_distinct(self):
        _,_,absent=N.original_methods(classfile())
        _,_,present=N.original_methods(classfile(attributes=[('RuntimeVisibleAnnotations',b'')]))
        self.assertIsNone(absent[0]['annotations']);self.assertEqual(present[0]['annotations'],'')
        self.assertIsNone(present[0]['annotation_default'])

    def test_all_raw_reflection_attributes_survive(self):
        _,_,rows=N.original_methods(classfile(attributes=[
            ('Signature','<T:Ljava/lang/Object;>()TT;'),('RuntimeVisibleAnnotations',b'\0\0'),
            ('RuntimeVisibleParameterAnnotations',b'\0'),('AnnotationDefault',b's\0\1'),
            ('RuntimeVisibleTypeAnnotations',b'\0\0'),('MethodParameters',b'\0')]))
        row=rows[0]
        self.assertEqual(row['signature'],'<T:Ljava/lang/Object;>()TT;')
        self.assertEqual(row['annotations'],'0000');self.assertEqual(row['parameter_annotations'],'00')
        self.assertEqual(row['annotation_default'],'730001');self.assertEqual(row['type_annotations'],'0000')
        self.assertEqual(row['method_parameters'],'00');self.assertEqual(row['access'],0x1041)

    def test_duplicate_attribute_rejected(self):
        with self.assertRaises(ValueError):N.original_methods(classfile(attributes=[('AnnotationDefault',b's\0\1')]*2))

    def test_original_source_truncation_or_magic_changes_rejected(self):
        raw=classfile()
        for changed in (b'\0'+raw[1:],raw[:-1],raw[:20],raw+b'\0'):
            with self.subTest(size=len(changed)),self.assertRaises((ValueError,IndexError,struct.error)):
                N.original_methods(changed)

    def test_exception_must_reference_a_class_constant(self):
        with self.assertRaises(ValueError):N.original_methods(classfile(exception_index=0))


class MethodMachineContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assembler=Path('D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe')
        if not assembler.is_file():raise unittest.SkipTest('Development ML64 is unavailable')
        spec=importlib.util.spec_from_file_location('normal_methods_machine_test',ROOT/'scripts/normal-methods-candidate.py')
        cls.B=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.B)
        cls.output=ROOT/'.boom/normal-methods/machine-tests'/uuid4().hex;cls.output.mkdir(parents=True)
        text='''option casemap:none
EXTERN boom_heap_alloc:PROC
EXTERN boom_heap_ptr:BYTE
.const
ALIGN 8
PUBLIC boom_fixture_metadata
boom_fixture_metadata QWORD OFFSET boom_heap_ptr
.code
PUBLIC boom_fixture_method
boom_fixture_method PROC FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 call boom_heap_alloc
 add rsp,40
 ret
boom_fixture_method ENDP
END
'''
        cls.objects=[]
        for name in ('first','different-source-name'):
            asm=cls.output/(name+'.asm');obj=asm.with_suffix('.obj');asm.write_text(text)
            run=subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
            if run.returncode:raise AssertionError(run.stdout.decode(errors='replace'))
            cls.objects.append(obj)
        cls.raw=cls.objects[0].read_bytes();cls.fingerprint=cls.B.normalized_coff(cls.objects[0])

    def section(self,name):
        raw=self.raw
        for i in range(struct.unpack_from('<H',raw,2)[0]):
            at=20+i*40
            if raw[at:at+8].rstrip(b'\0').decode()==name:return at
        self.fail('Fixture section missing: '+name)

    def changed(self,raw):
        path=self.output/('tamper-'+uuid4().hex+'.obj');path.write_bytes(raw)
        return self.B.normalized_coff(path)

    def test_actual_reassembly_is_filename_independent(self):
        self.assertEqual(self.fingerprint,self.B.normalized_coff(self.objects[1]))

    def test_actual_instruction_byte_change_is_detected(self):
        raw=bytearray(self.raw);at=self.section('.text$mn');data=struct.unpack_from('<I',raw,at+20)[0]
        raw[data+1]^=1;self.assertNotEqual(self.fingerprint,self.changed(raw))

    def test_section_flag_change_is_detected(self):
        raw=bytearray(self.raw);at=self.section('.rdata')+36
        struct.pack_into('<I',raw,at,struct.unpack_from('<I',raw,at)[0]^0x80000000)
        self.assertNotEqual(self.fingerprint,self.changed(raw))

    def test_unwind_code_change_is_detected(self):
        raw=bytearray(self.raw);at=self.section('.xdata');data=struct.unpack_from('<I',raw,at+20)[0]
        raw[data+4]^=1;self.assertNotEqual(self.fingerprint,self.changed(raw))

    def test_pdata_relocation_change_is_detected(self):
        raw=bytearray(self.raw);at=self.section('.pdata');reloc=struct.unpack_from('<I',raw,at+24)[0]
        struct.pack_into('<H',raw,reloc+8,4);self.assertNotEqual(self.fingerprint,self.changed(raw))

    def test_invalid_auxiliary_relocation_target_is_rejected(self):
        raw=bytearray(self.raw);symbol_at,count=struct.unpack_from('<II',raw,8);aux=None;i=0
        while i<count:
            n=raw[symbol_at+i*18+17]
            if n:aux=i+1;break
            i+=n+1
        self.assertIsNotNone(aux);at=self.section('.pdata');reloc=struct.unpack_from('<I',raw,at+24)[0]
        struct.pack_into('<I',raw,reloc+4,aux)
        with self.assertRaises(ValueError):self.changed(raw)

    def test_nondebug_section_auxiliary_change_is_detected(self):
        raw=bytearray(self.raw);symbol_at,count=struct.unpack_from('<II',raw,8);i=0;changed=False
        while i<count:
            at=symbol_at+i*18;name=raw[at:at+8].rstrip(b'\0');aux=raw[at+17]
            if name==b'.rdata' and aux:
                raw[at+18+8]^=1;changed=True;break
            i+=aux+1
        self.assertTrue(changed);self.assertNotEqual(self.fingerprint,self.changed(raw))


if __name__=='__main__':unittest.main()
