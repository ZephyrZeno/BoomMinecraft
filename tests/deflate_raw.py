"""Actual ML64/LINK verifier mutation tests; no game/runtime registration."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import unittest
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('test_deflate_candidate',ROOT/'scripts/deflate-raw-candidate.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)


def sections(raw):
    result={}
    for i in range(struct.unpack_from('<H',raw,2)[0]):
        at=20+i*40;name=raw[at:at+8].rstrip(b'\0').decode()
        size,data,reloc=struct.unpack_from('<III',raw,at+16)
        result[name]=(size,data,reloc,struct.unpack_from('<H',raw,at+32)[0])
    return result


def symbol_rows(raw):
    symoff,count=struct.unpack_from('<II',raw,8);strings=symoff+count*18;rows={};i=0
    while i<count:
        at=symoff+i*18;name=bytes(raw[at:at+8])
        if name[:4]==b'\0'*4:
            start=strings+struct.unpack_from('<I',name,4)[0];end=raw.index(0,start);name=bytes(raw[start:end])
        else:name=name.rstrip(b'\0')
        rows[name.decode()]=(i,at)
        i+=1+raw[at+17]
    return rows


@unittest.skipUnless(os.name=='nt','Actual Microsoft AMD64 ML64/LINK fixture')
class DeflateMachineProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output=C.ART/'unittest-fixtures'/uuid4().hex
        cls.base=C.build(cls.output/'base',C.TOOLS/'ml64.exe',C.TOOLS/'link.exe')

    def clone(self):
        folder=self.output/self._testMethodName;folder.mkdir()
        row=json.loads(self.base.read_text(encoding='utf-8'))
        for name,file in [('assembly','kernel.asm'),('object','kernel.obj'),('image','kernel.dll')]:
            target=folder/file;shutil.copyfile(row[name]['path'],target);row[name]=C.artifact(target)
        rsp=folder/'link.rsp';rsp.write_text(C.response(Path(row['object']['path']),Path(row['image']['path'])),encoding='utf-8',newline='\n')
        row['response']=C.artifact(rsp)
        return folder/'candidate.json',row

    def reject(self,path,row,pattern):
        C.write(path,row)
        with self.assertRaisesRegex(ValueError,pattern):C.verify(path)

    def mutate_object(self,edit,pattern='Actual COFF'):
        path,row=self.clone();obj=Path(row['object']['path']);raw=bytearray(obj.read_bytes());edit(raw)
        obj.write_bytes(raw);row['object']=C.artifact(obj);self.reject(path,row,pattern)

    def test_instruction_mutation_with_refreshed_digest(self):
        def edit(raw):
            rows=sections(raw);raw[(rows.get('.text$mn') or rows['.text'])[1]]^=1
        self.mutate_object(edit)

    def test_readonly_distance_table_mutation(self):
        def edit(raw):
            _,at=symbol_rows(raw)['boom_deflate_dr_distance_base'];value=struct.unpack_from('<I',raw,at+8)[0]
            raw[sections(raw)['.rdata'][1]+value]^=1
        self.mutate_object(edit)

    def test_relocation_target_changes_with_same_public_symbols(self):
        def edit(raw):
            rows=symbol_rows(raw);source=rows['boom_deflate_dr_length_base'][0];target=rows['boom_deflate_dr_distance_base'][0]
            rows_by_section=sections(raw);_,_,reloc,count=rows_by_section.get('.text$mn') or rows_by_section['.text']
            for i in range(count):
                at=reloc+i*10
                if struct.unpack_from('<I',raw,at+4)[0]==source:struct.pack_into('<I',raw,at+4,target);return
            self.fail('Fixture did not actually have a length-table relocation')
        self.mutate_object(edit)

    def test_unwind_mutation(self):
        def edit(raw):raw[sections(raw)['.xdata'][1]]^=1
        self.mutate_object(edit)

    def test_private_helper_cannot_be_promoted_to_new_public(self):
        def edit(raw):
            _,at=symbol_rows(raw)['boom_deflate_dr_bits'];self.assertNotEqual(raw[at+16],2);raw[at+16]=2
        self.mutate_object(edit,'exactly one public function')

    def test_pe_header_not_just_execution_sections_is_covered(self):
        path,row=self.clone();image=Path(row['image']['path']);raw=bytearray(image.read_bytes())
        pe=struct.unpack_from('<I',raw,60)[0];raw[pe+24+56]^=1
        image.write_bytes(raw);row['image']=C.artifact(image);self.reject(path,row,'Actual PE')

    def test_pe_instruction_mutation_with_refreshed_digest(self):
        path,row=self.clone();image=Path(row['image']['path']);raw=bytearray(image.read_bytes())
        pe=struct.unpack_from('<I',raw,60)[0];opt=struct.unpack_from('<H',raw,pe+20)[0];first=pe+24+opt
        self.assertEqual(raw[first:first+5],b'.text');raw[struct.unpack_from('<I',raw,first+20)[0]]^=1
        image.write_bytes(raw);row['image']=C.artifact(image);self.reject(path,row,'Actual PE')

    def test_pe_imports_cannot_be_added(self):
        path,row=self.clone();image=Path(row['image']['path']);raw=bytearray(image.read_bytes())
        pe=struct.unpack_from('<I',raw,60)[0];struct.pack_into('<II',raw,pe+24+112+8,1,1)
        image.write_bytes(raw);row['image']=C.artifact(image);self.reject(path,row,'imports.*forbidden')

    def test_unexpected_rsp_parameter(self):
        path,row=self.clone();rsp=Path(row['response']['path']);rsp.write_text(rsp.read_text()+' /FORCE\n',encoding='utf-8')
        row['response']=C.artifact(rsp);self.reject(path,row,'exact link arguments')

    def test_false_abi_metadata(self):
        path,row=self.clone();row['abi']['job_bytes']=32;self.reject(path,row,'ABI changed')


if __name__=='__main__':unittest.main()
