"""Real ml64 checks for fresh split source/COFF receipts without a monolithic object."""
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import unittest
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('fresh_parallel_assembly',ROOT/'scripts/parallel-diagnostic-assembly.py')
H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)
ML64=Path(os.environ.get('BOOM_TEST_ML64','D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe'))
SOURCE='''option casemap:none
EXTERN boom_external:PROC
PUBLIC boom_first
PUBLIC boom_first_body
.data?
ALIGN 8
PUBLIC boom_probe_static_roots
boom_probe_static_roots LABEL QWORD
PUBLIC boom_root0
boom_root0 QWORD ?
boom_root1 QWORD ?
.const
PUBLIC boom_probe_static_root_count
boom_probe_static_root_count QWORD 2
.code
boom_first PROC
 jmp boom_first_body
boom_first ENDP
boom_first_body PROC FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 lea rax,boom_root1
 call boom_external
 add rsp,40
 ret
boom_first_body ENDP
END
'''


class FreshParallel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ML64.is_file():raise unittest.SkipTest('Real Windows ml64 is required')
        cls.output=ROOT/'.boom/fresh-parallel-assembly-tests'/uuid4().hex;cls.output.mkdir(parents=True)

    def source(self,text=SOURCE):
        directory=self.output/uuid4().hex;directory.mkdir()
        path=directory/'initialization-closure.asm';path.write_text(text,encoding='utf-8')
        raw=path.read_bytes();expected={n:hashlib.sha256(H.P.normalized_source(raw[a:b])).hexdigest()
                                      for n,(a,b) in H.B.procedure_spans(raw).items()}
        self.assertFalse(path.with_suffix('.obj').exists())
        return path,expected,directory/'split'

    def built(self):
        source,expected,output=self.source()
        prepared=H.prepare(source,output,expected,budget_bytes=128)
        receipt=H.assemble(prepared,ML64,workers=2)
        return source,expected,prepared,receipt

    def test_real_fresh_source_coff_roots_unwind_and_determinism(self):
        source,expected,prepared,receipt=self.built()
        first=H.verify(receipt,source,expected);second=H.verify(receipt,source,expected)
        self.assertEqual(first,second)
        self.assertEqual(first['source_functions'],2)
        self.assertEqual(first['framed_functions'],1)
        self.assertEqual(first['static_roots'],dict(section='.bss',offset=0,cells=2,bytes=16,named_entries=2))
        self.assertEqual(receipt['promoted_data'],['boom_root1'])
        self.assertEqual(first['imports'],['boom_external'])
        self.assertFalse(first['monolithic_reference_used'])
        self.assertFalse(first['monolithic_binary_equivalence'])
        self.assertFalse(source.with_suffix('.obj').exists())
        code=next(u for u in prepared['units'] if u['role']=='code')
        self.assertEqual(code['functions'],['boom_first','boom_first_body'])
        self.assertEqual(code['extern_types']['boom_root1'],'QWORD')

    def test_private_code_cannot_be_promoted(self):
        source,expected,output=self.source(SOURCE.replace('PUBLIC boom_first_body\n',''))
        with self.assertRaisesRegex(ValueError,'Private procedures'):H.prepare(source,output,expected)

    def test_wrong_original_normalized_function_hash_is_rejected(self):
        source,expected,output=self.source();expected['boom_first']='0'*64
        with self.assertRaisesRegex(ValueError,'normalized procedure hash'):H.prepare(source,output,expected)

    def test_source_root_count_mismatch_is_rejected(self):
        source,expected,output=self.source(SOURCE.replace('static_root_count QWORD 2','static_root_count QWORD 3'))
        with self.assertRaisesRegex(ValueError,'root declarations'):H.prepare(source,output,expected)

    def test_a_function_in_promotion_list_is_rejected(self):
        source,expected,_,receipt=self.built();receipt=copy.deepcopy(receipt)
        receipt['promoted_data']=sorted(receipt['promoted_data']+['boom_first'])
        with self.assertRaisesRegex(ValueError,'promotions'):H.verify(receipt,source,expected)

    def test_actual_coff_root_alias_is_rejected(self):
        source,expected,_,receipt=self.built();unit=receipt['units'][0];path=Path(unit['object']['path'])
        coff=H.P.Coff(path);index=next(i for i,s in enumerate(coff.index) if s and s['name']=='boom_root1')
        raw=bytearray(path.read_bytes());symbols=struct.unpack_from('<I',raw,8)[0]
        struct.pack_into('<I',raw,symbols+index*18+8,0);path.write_bytes(raw);unit['object']=H.artifact(path)
        with self.assertRaisesRegex(ValueError,'root moved'):H.verify(receipt,source,expected)

    def test_actual_unwind_start_outside_source_procedure_is_rejected(self):
        source,expected,_,receipt=self.built();unit=next(u for u in receipt['units'] if u['role']=='code')
        path=Path(unit['object']['path']);raw=bytearray(path.read_bytes());sections=struct.unpack_from('<H',raw,2)[0]
        for i in range(sections):
            at=20+i*40
            if raw[at:at+8].rstrip(b'\0')==b'.pdata':
                offset=struct.unpack_from('<I',raw,at+20)[0];value=struct.unpack_from('<I',raw,offset)[0]
                struct.pack_into('<I',raw,offset,value+1);break
        else:self.fail('Real FRAME procedure emitted no unwind range')
        path.write_bytes(raw);unit['object']=H.artifact(path)
        with self.assertRaisesRegex(ValueError,'source procedure'):H.verify(receipt,source,expected)


if __name__=='__main__':unittest.main()
