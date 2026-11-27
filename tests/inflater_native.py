"""Source-bound Inflater component machine integrity over a real ML64 object."""
import importlib.util
import json
import os
from pathlib import Path
import struct
import unittest
from uuid import uuid4
from tests.deflate_raw import sections,symbol_rows

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('inflater_native_integrity',ROOT/'scripts/inflater-candidate.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)


@unittest.skipUnless(os.name=='nt','Actual AMD64 MASM candidate fixture')
class InflaterNativeMachine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=ROOT/'.boom/inflater-normal/source-b/candidate.json'
        if not path.exists():raise unittest.SkipTest('Run the separately verified original-source Inflater candidate builder first')
        cls.row=B.S.read(path);cls.text=Path(cls.row['assembly']['path']).read_text(encoding='utf-8')
        B.S.checked(cls.row['assembly']);B.S.checked(cls.row['object'])
        cls.output=B.S.ART/'inflater-normal/integrity-tests'/uuid4().hex;cls.output.mkdir(parents=True)

    def check_mutation(self,edit):
        raw=bytearray(Path(self.row['object']['path']).read_bytes());edit(raw);obj=self.output/(self._testMethodName+'.obj');obj.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'Actual Inflater COFF'):
            B.machine(self.text,obj,Path(self.row['assembler']['path']))

    def test_service_instruction_is_bound_to_source(self):
        def edit(raw):
            sec=sections(raw);_,at=symbol_rows(raw)['boom_provider_inflater_service'];value=struct.unpack_from('<I',raw,at+8)[0]
            raw[(sec.get('.text$mn') or sec['.text'])[1]+value]^=1
        self.check_mutation(edit)

    def test_lookup_lock_lifetime_call_relocation_is_bound(self):
        def edit(raw):
            syms=symbol_rows(raw);before=syms['AcquireSRWLockShared'][0];after=syms['ReleaseSRWLockShared'][0]
            sec=sections(raw);_,_,reloc,count=sec.get('.text$mn') or sec['.text']
            for i in range(count):
                at=reloc+10*i
                if struct.unpack_from('<I',raw,at+4)[0]==before:struct.pack_into('<I',raw,at+4,after);return
            self.fail('Expected real lifetime-lock call relocation')
        self.check_mutation(edit)

    def test_typed_exception_constructor_relocation_is_bound(self):
        def edit(raw):
            syms=symbol_rows(raw);meta=self.row['metadata']['source'];ctors=[m['method'] for m in meta['java_callbacks'] if m['name']=='<init>']
            before=syms['boom_m'+str(ctors[0])][0];after=syms['boom_m'+str(ctors[1])][0];_,_,reloc,count=sections(raw)['.rdata']
            for i in range(count):
                at=reloc+10*i
                if struct.unpack_from('<I',raw,at+4)[0]==before:struct.pack_into('<I',raw,at+4,after);return
            self.fail('Expected real original-Java exception constructor pointer')
        self.check_mutation(edit)

    def test_unwind_is_bound(self):
        def edit(raw):raw[sections(raw)['.xdata'][1]]^=1
        self.check_mutation(edit)


if __name__=='__main__':unittest.main()
