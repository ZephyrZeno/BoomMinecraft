"""Negative cases over the actual 42-entry typed Unsafe COFF prefix."""
import importlib.util
import json
import os
from pathlib import Path
import struct
import unittest
from uuid import uuid4
from tests.deflate_raw import sections,symbol_rows

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('jimage_unsafe_integrity',ROOT/'scripts/jimage-unsafe-read-candidate.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)


@unittest.skipUnless(os.name=='nt','Actual Windows AMD64 typed candidate')
class JimageUnsafePrefix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=ROOT/'.boom/jimage-unsafe-read/source-c/candidate.json'
        if not path.exists():raise unittest.SkipTest('Build the separately source/frame verified JIMAGE read candidate first')
        cls.row=B.S.read(path);cls.methods=cls.row['metadata']['source']['methods'];cls.old=B.checked(cls.row['metadata']['original_unit']['object']);cls.obj=B.checked(cls.row['object'])
        cls.output=B.ART/'prefix-negatives'/uuid4().hex;cls.output.mkdir(parents=True)
        B.prefix_proof(cls.old,cls.obj,cls.methods)

    def reject(self,edit):
        raw=bytearray(self.obj.read_bytes());edit(raw);path=self.output/(self._testMethodName+'.obj');path.write_bytes(raw)
        with self.assertRaises(ValueError):B.prefix_proof(self.old,path,self.methods)

    def route(self,raw,operation,destination):
        syms=symbol_rows(raw);ident=next(m['method'] for m in self.methods if m['operation']==operation);_,entry=syms[f'boom_m{ident}_native'];start=struct.unpack_from('<I',raw,entry+8)[0]
        sec=sections(raw);_,_,reloc,count=sec.get('.text$mn') or sec['.text']
        for i in range(count):
            at=reloc+10*i;offset=struct.unpack_from('<I',raw,at)[0]
            if start<=offset<start+32 and raw[(sec.get('.text$mn') or sec['.text'])[1]+offset-1]==0xe9:
                struct.pack_into('<I',raw,at+4,syms[destination][0]);return
        self.fail('Actual terminal service relocation missing')

    def test_original_adapter_instruction_unchanged(self):
        def edit(raw):
            _,symbol=symbol_rows(raw)[f"boom_m{self.methods[0]['method']}"];value=struct.unpack_from('<I',raw,symbol+8)[0];sec=sections(raw)
            raw[(sec.get('.text$mn') or sec['.text'])[1]+value]^=1
        self.reject(edit)

    def test_write_route_cannot_be_added_to_read_profile(self):
        self.reject(lambda raw:self.route(raw,21,B.C.SERVICE))

    def test_required_byte_read_cannot_fall_back_to_old_unprovided_domain(self):
        self.reject(lambda raw:self.route(raw,2,'boom_java_unsafe_memory'))

    def test_original_Unsafe_class_relocation_is_not_replaceable(self):
        def edit(raw):
            syms=symbol_rows(raw);before=syms['boom_class'+str(self.row['metadata']['source']['owner'])][0];after=syms['boom_java_unsafe_field_pool'][0]
            sec=sections(raw);_,_,reloc,count=sec.get('.text$mn') or sec['.text']
            for i in range(count):
                at=reloc+10*i
                if struct.unpack_from('<I',raw,at+4)[0]==before:struct.pack_into('<I',raw,at+4,after);return
            self.fail('Actual normal Unsafe descriptor relocation missing')
        self.reject(edit)

    def test_original_adapter_unwind_is_not_replaceable(self):
        self.reject(lambda raw:raw.__setitem__(sections(raw)['.xdata'][1],raw[sections(raw)['.xdata'][1]]^1))


if __name__=='__main__':unittest.main()
