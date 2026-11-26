"""Actual streaming-kernel COFF/PE/ABI-proof tampering tests."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import unittest
from uuid import uuid4
from tests.deflate_raw import sections,symbol_rows

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('test_stream_candidate',ROOT/'scripts/deflate-stream-candidate.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)


@unittest.skipUnless(os.name=='nt','Actual Microsoft AMD64 ML64/LINK fixture')
class DeflateStreamMachineProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output=C.ART/'unittest-fixtures'/uuid4().hex
        cls.base=C.build(cls.output/'base',C.C.TOOLS/'ml64.exe',C.C.TOOLS/'link.exe')

    def clone(self):
        folder=self.output/self._testMethodName;folder.mkdir();row=json.loads(self.base.read_text(encoding='utf-8'))
        for name,file in [('assembly','stream.asm'),('object','stream.obj'),('image','stream.dll')]:
            target=folder/file;shutil.copyfile(row[name]['path'],target);row[name]=C.artifact(target)
        rsp=folder/'link.rsp';rsp.write_text(C.response(Path(row['object']['path']),Path(row['image']['path'])),encoding='utf-8',newline='\n')
        row['response']=C.artifact(rsp);return folder/'candidate.json',row

    def reject(self,path,row,pattern):
        C.write(path,row)
        with self.assertRaisesRegex(ValueError,pattern):C.verify(path)

    def mutate(self,edit,pattern='Actual streaming COFF'):
        path,row=self.clone();p=Path(row['object']['path']);raw=bytearray(p.read_bytes());edit(raw)
        p.write_bytes(raw);row['object']=C.artifact(p);self.reject(path,row,pattern)

    def test_resume_machine_instruction_is_not_just_symbol_checked(self):
        def edit(raw):
            rows=sections(raw);_,at=symbol_rows(raw)['boom_deflate_stream_step'];value=struct.unpack_from('<I',raw,at+8)[0]
            raw[(rows.get('.text$mn') or rows['.text'])[1]+value]^=1
        self.mutate(edit)

    def test_relocation_retarget_with_same_two_exports(self):
        def edit(raw):
            syms=symbol_rows(raw);old=syms['boom_ds_length_base'][0];new=syms['boom_ds_distance_base'][0]
            sec=sections(raw);_,_,reloc,count=sec.get('.text$mn') or sec['.text']
            for i in range(count):
                at=reloc+10*i
                if struct.unpack_from('<I',raw,at+4)[0]==old:struct.pack_into('<I',raw,at+4,new);return
            self.fail('Fixture must have the actual length-base relocation')
        self.mutate(edit)

    def test_streaming_unwind_is_machine_checked(self):
        def edit(raw):raw[sections(raw)['.xdata'][1]]^=1
        self.mutate(edit)

    def test_private_helper_promotion_is_forbidden(self):
        def edit(raw):
            _,at=symbol_rows(raw)['boom_ds_bits'];self.assertNotEqual(raw[at+16],2);raw[at+16]=2
        self.mutate(edit,'two exact exports')

    def test_complete_pe_header_is_covered(self):
        path,row=self.clone();p=Path(row['image']['path']);raw=bytearray(p.read_bytes());pe=struct.unpack_from('<I',raw,60)[0]
        raw[pe+24+56]^=1;p.write_bytes(raw);row['image']=C.artifact(p);self.reject(path,row,'complete PE differs')

    def test_decoder_import_cannot_be_inserted(self):
        path,row=self.clone();p=Path(row['image']['path']);raw=bytearray(p.read_bytes());pe=struct.unpack_from('<I',raw,60)[0]
        struct.pack_into('<II',raw,pe+24+112+8,1,1);p.write_bytes(raw);row['image']=C.artifact(p);self.reject(path,row,'imports.*forbidden')

    def test_extra_link_parameter_is_rejected(self):
        path,row=self.clone();p=Path(row['response']['path']);p.write_text(p.read_text()+' /FORCE\n',encoding='utf-8')
        row['response']=C.artifact(p);self.reject(path,row,'exact link arguments')

    def test_claimed_history_or_state_size_cannot_change(self):
        path,row=self.clone();row['abi']['history_bytes']=4096;self.reject(path,row,'ABI pins differ')


if __name__=='__main__':unittest.main()
