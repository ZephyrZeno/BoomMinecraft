"""Actual copy-core and original native adapter machine-proof negatives."""
import copy
import importlib.util
import os
from pathlib import Path
import struct
import unittest
from uuid import uuid4
from tests.deflate_raw import sections,symbol_rows

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('jimage_copy_integrity',ROOT/'scripts/jimage-unsafe-copy-candidate.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)


@unittest.skipUnless(os.name=='nt','Actual AMD64 MASM copy candidate')
class JimageUnsafeCopyMachine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=B.ART/'source-a/candidate.json'
        if not path.exists():raise unittest.SkipTest('Build the separately current-source verified copy candidate first')
        cls.row=B.S.read(path);cls.output=B.ART/'machine-negatives'/uuid4().hex;cls.output.mkdir(parents=True)

    def reject(self,key,edit):
        row=copy.deepcopy(self.row);raw=bytearray(B.checked(row[key]).read_bytes());edit(raw);path=self.output/(self._testMethodName+'.obj');path.write_bytes(raw);row[key]=B.S.artifact(path)
        with self.assertRaisesRegex(ValueError,'Actual copy code/data/symbols/relocations/unwind differs'):
            B.machine(row,row['metadata'])

    def test_destination_byte_type_cannot_be_weakened_to_boolean(self):
        def edit(raw):
            sec=sections(raw);_,offset,_,_=sec.get('.text$mn') or sec['.text'];needle=bytes.fromhex('48 81 7f f8 08 01 00 00');positions=[i for i in range(offset,len(raw)) if raw[i:i+len(needle)]==needle]
            self.assertEqual(len(positions),1,'Actual physical byte-array tag comparison');raw[positions[0]+4]=4
        self.reject('core_object',edit)

    def test_signed_length_guard_must_test_the_actual_length(self):
        def edit(raw):
            sec=sections(raw);length,offset,_,_=sec.get('.text$mn') or sec['.text'];at=raw.find(bytes.fromhex('48 85 ed'),offset,offset+length);self.assertNotEqual(at,-1);raw[at+2]=0xc0
        self.reject('core_object',edit)

    def test_normal_heap_membership_call_cannot_be_retargeted(self):
        self.reject('core_object',lambda raw:self.retarget(raw,'boom_heap_contains','AcquireSRWLockShared'))

    def test_shared_read_lock_must_be_released(self):
        self.reject('core_object',lambda raw:self.retarget(raw,'ReleaseSRWLockShared','AcquireSRWLockShared'))

    def retarget(self,raw,before,after):
        syms=symbol_rows(raw);section=sections(raw);_,_,reloc,count=section.get('.text$mn') or section['.text']
        for i in range(count):
            at=reloc+10*i
            if struct.unpack_from('<I',raw,at+4)[0]==syms[before][0]:struct.pack_into('<I',raw,at+4,syms[after][0]);return
        self.fail('Expected actual external call relocation')

    def test_native_adapter_unwind_is_bound(self):
        def edit(raw):at=sections(raw)['.xdata'][1];raw[at]^=1
        self.reject('object',edit)


if __name__=='__main__':unittest.main()
