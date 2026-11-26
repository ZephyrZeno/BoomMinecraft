"""Actual wrapper/raw source binding and ML64/LINK machine-proof mutations."""
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
spec=importlib.util.spec_from_file_location('test_zlib_candidate',ROOT/'scripts/zlib-stream-candidate.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)


@unittest.skipUnless(os.name=='nt','Actual Microsoft AMD64 ML64/LINK fixture')
class ZlibMachineProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output=C.ART/'unittest-fixtures'/uuid4().hex;tools=C.B.C.TOOLS
        raw=C.B.build(C.B.ART/'zlib-unittest-raw'/uuid4().hex,tools/'ml64.exe',tools/'link.exe')
        cls.base=C.build(raw,cls.output/'base',tools/'ml64.exe',tools/'link.exe')

    def clone(self):
        folder=self.output/self._testMethodName;folder.mkdir();row=json.loads(self.base.read_text(encoding='utf-8'))
        for name,file in [('assembly','zlib.asm'),('object','zlib.obj'),('image','zlib.dll')]:
            p=folder/file;shutil.copyfile(row[name]['path'],p);row[name]=C.artifact(p)
        rsp=folder/'link.rsp';rsp.write_text(C.response(Path(row['object']['path']),Path(row['image']['path']),Path(row['raw']['object']['path'])),encoding='utf-8',newline='\n')
        row['response']=C.artifact(rsp);return folder/'candidate.json',row

    def reject(self,path,row,pattern):
        C.write(path,row)
        with self.assertRaisesRegex(ValueError,pattern):C.verify(path)

    def mutate(self,edit,pattern='Actual wrapper COFF'):
        path,row=self.clone();p=Path(row['object']['path']);raw=bytearray(p.read_bytes());edit(raw)
        p.write_bytes(raw);row['object']=C.artifact(p);self.reject(path,row,pattern)

    def test_Adler_machine_instruction_not_only_exports(self):
        def edit(raw):
            sec=sections(raw);_,at=symbol_rows(raw)['boom_zw_adler'];value=struct.unpack_from('<I',raw,at+8)[0]
            raw[(sec.get('.text$mn') or sec['.text'])[1]+value]^=1
        self.mutate(edit)

    def test_raw_callback_retarget_with_same_import_names(self):
        def edit(raw):
            syms=symbol_rows(raw);old=syms['boom_deflate_stream_reset'][0];new=syms['boom_deflate_stream_step'][0]
            sec=sections(raw);_,_,reloc,count=sec.get('.text$mn') or sec['.text']
            for i in range(count):
                at=reloc+i*10
                if struct.unpack_from('<I',raw,at+4)[0]==old:struct.pack_into('<I',raw,at+4,new);return
            self.fail('Actual raw reset relocation required')
        self.mutate(edit)

    def test_wrapper_unwind_mutation(self):
        def edit(raw):raw[sections(raw)['.xdata'][1]]^=1
        self.mutate(edit)

    def test_private_wrapper_helper_promotion(self):
        def edit(raw):
            _,at=symbol_rows(raw)['boom_zw_byte'];self.assertNotEqual(raw[at+16],2);raw[at+16]=2
        self.mutate(edit,'Wrapper exports/raw imports differ')

    def test_PE_header_is_complete_image_checked(self):
        path,row=self.clone();p=Path(row['image']['path']);raw=bytearray(p.read_bytes());pe=struct.unpack_from('<I',raw,60)[0]
        raw[pe+24+56]^=1;p.write_bytes(raw);row['image']=C.artifact(p);self.reject(path,row,'complete PE differs')

    def test_foreign_decoder_import_forbidden(self):
        path,row=self.clone();p=Path(row['image']['path']);raw=bytearray(p.read_bytes());pe=struct.unpack_from('<I',raw,60)[0]
        struct.pack_into('<II',raw,pe+24+112+8,1,1);p.write_bytes(raw);row['image']=C.artifact(p);self.reject(path,row,'imports.*forbidden')

    def test_extra_RSP_input_or_flag_is_not_ignored(self):
        path,row=self.clone();p=Path(row['response']['path']);p.write_text(p.read_text()+' /FORCE\nextra.obj\n',encoding='utf-8')
        row['response']=C.artifact(p);self.reject(path,row,'exact link arguments')

    def test_private_raw_layout_version_cannot_be_redeclared(self):
        path,row=self.clone();row['abi']['raw_private_layout']['match_distance']=100;self.reject(path,row,'private-layout pins differ')

    def test_replaced_raw_object_cannot_be_certified_by_old_receipt(self):
        path,row=self.clone();p=path.parent/'changed-raw.obj';shutil.copyfile(row['raw']['object']['path'],p);raw=bytearray(p.read_bytes());sec=sections(raw)
        raw[(sec.get('.text$mn') or sec['.text'])[1]]^=1;p.write_bytes(raw);row['raw']['object']=C.artifact(p)
        self.reject(path,row,'Actual frozen raw contract differs')


if __name__=='__main__':unittest.main()
