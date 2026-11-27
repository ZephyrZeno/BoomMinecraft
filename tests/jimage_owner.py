"""Reject modified native mapping-owner machines, not only matching symbols."""
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
spec=importlib.util.spec_from_file_location('unit_jimage_owner',ROOT/'scripts/jimage-owner-candidate.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)


@unittest.skipUnless(os.name=='nt','Actual AMD64 Microsoft assembler/linker fixtures')
class MappingOwnerMachine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=B.ART/'unit-fixtures'/uuid4().hex
        cls.base=B.build(cls.folder/'base')

    def clone(self):
        directory=self.folder/self._testMethodName;directory.mkdir()
        row=json.loads(self.base.read_text())
        for key,name in [('assembly','owner.asm'),('object','owner.obj'),('image','owner.dll')]:
            target=directory/name;shutil.copyfile(row[key]['path'],target);row[key]=B.artifact(target)
        rsp=directory/'link.rsp'
        rsp.write_text(B.response(Path(row['object']['path']),Path(row['image']['path']),Path(row['kernel32']['path'])),encoding='utf-8',newline='\n')
        row['response']=B.artifact(rsp)
        return directory/'candidate.json',row

    def reject(self,path,row,message):
        B.write(path,row)
        with self.assertRaisesRegex(ValueError,message):B.verify(path)

    def mutate_object(self,edit,message='Actual owner instructions'):
        path,row=self.clone();target=Path(row['object']['path']);data=bytearray(target.read_bytes());edit(data)
        target.write_bytes(data);row['object']=B.artifact(target);self.reject(path,row,message)

    def test_actual_instruction_change(self):
        def edit(data):
            table=sections(data);data[(table.get('.text$mn') or table['.text'])[1]]^=1
        self.mutate_object(edit)

    def test_Win32_relocation_retarget_keeps_import_names(self):
        def edit(data):
            symbols=symbol_rows(data);old=symbols['CreateFileW'][0];new=symbols['CloseHandle'][0]
            table=sections(data);_,_,at,count=table.get('.text$mn') or table['.text']
            for i in range(count):
                pos=at+10*i
                if struct.unpack_from('<I',data,pos+4)[0]==old:struct.pack_into('<I',data,pos+4,new);return
            self.fail('Expected real CreateFileW relocation')
        self.mutate_object(edit)

    def test_unwind_change(self):
        self.mutate_object(lambda data:data.__setitem__(sections(data)['.xdata'][1],data[sections(data)['.xdata'][1]]^1))

    def test_auxiliary_symbol_change(self):
        def edit(data):
            _,at=symbol_rows(data)['.pdata'];self.assertGreater(data[at+17],0);data[at+18]^=1
        self.mutate_object(edit)

    def test_private_helper_promoted(self):
        def edit(data):
            _,at=symbol_rows(data)['jio_record_close'];self.assertNotEqual(data[at+16],2);data[at+16]=2
        self.mutate_object(edit)

    def test_writable_execution_section(self):
        def edit(data):
            count=struct.unpack_from('<H',data,2)[0]
            for i in range(count):
                at=20+40*i
                if bytes(data[at:at+8]).startswith(b'.text'):
                    flags=struct.unpack_from('<I',data,at+36)[0];struct.pack_into('<I',data,at+36,flags|0x80000000);return
            self.fail('Expected executable section')
        self.mutate_object(edit)

    def test_complete_PE_header_checked(self):
        path,row=self.clone();p=Path(row['image']['path']);data=bytearray(p.read_bytes());at=struct.unpack_from('<I',data,60)[0]
        data[at+24+56]^=1;p.write_bytes(data);row['image']=B.artifact(p);self.reject(path,row,'complete owner PE')

    def test_extra_library_or_link_flag_rejected(self):
        path,row=self.clone();p=Path(row['response']['path']);p.write_text(p.read_text()+'/FORCE\n"unrequested.lib"\n')
        row['response']=B.artifact(p);self.reject(path,row,'exact LINK response')

    def test_source_candidate_cannot_claim_execution(self):
        path,row=self.clone();row['executed']=True;self.reject(path,row,'candidate scope')


if __name__=='__main__':unittest.main()
