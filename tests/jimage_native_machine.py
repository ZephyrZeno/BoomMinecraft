"""Physical symbol and section mutations must fail complete JIMAGE checks."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import struct
import unittest
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('test_complete_jimage_machine',ROOT/'scripts/jimage-native-machine.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)


def section(raw,name):
    count=struct.unpack_from('<H',raw,2)[0]
    return next(20+40*i for i in range(count) if raw[20+40*i:28+40*i].rstrip(b'\0')==name.encode())


def exported_symbol(raw,name):
    table,count=struct.unpack_from('<II',raw,8);strings=table+18*count;index=0
    while index<count:
        at=table+18*index;label,value,number,kind,storage,aux=struct.unpack_from('<8sIhHBB',raw,at)
        if label[:4]==b'\0'*4:
            start=strings+struct.unpack_from('<I',label,4)[0];label=raw[start:raw.index(b'\0',start)]
        else:label=label.rstrip(b'\0')
        if label.decode()==name and storage==2 and number>0:return at
        index+=aux+1
    raise AssertionError('Expected actual exported native symbol '+name)


@unittest.skipUnless(os.name=='nt' and B.ASSEMBLER.is_file(),'Actual Windows AMD64 assembler required')
class CompleteJimageMachine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths={'map':B.ART/'source-bound-v176-c/candidate.json',
            'library':B.ART/'library-source-v178-c/candidate.json'}
        if not all(p.is_file() for p in cls.paths.values()):
            raise unittest.SkipTest('Build both current source candidates before their physical machine checks')
        cls.out=B.ART/'complete-machine-tests'/uuid4().hex;cls.out.mkdir(parents=True)

    def mutated(self,kind,mutate):
        row=copy.deepcopy(B.S.read(self.paths[kind]));raw=bytearray(B.S.checked(row['object']).read_bytes())
        mutate(raw,row);folder=self.out/(self._testMethodName+'-'+kind);folder.mkdir()
        obj=folder/'changed.obj';obj.write_bytes(raw);row['object']=B.S.artifact(obj)
        candidate=folder/'candidate.json';candidate.write_text(json.dumps(row)+'\n')
        with self.assertRaisesRegex(ValueError,'Complete JIMAGE COFF'):
            B.verify(candidate,kind,folder/'actual-check')

    def test_both_current_canonical_objects_pass(self):
        for kind,path in self.paths.items():
            with self.subTest(kind=kind):
                proof=B.S.read(B.verify(path,kind,self.out/('positive-'+kind)))
                self.assertTrue(proof['complete_symbol_values_types_storage_and_auxiliary_bytes_verified'])
                self.assertFalse(proof['normal_native_adapter_executed'])

    def test_unchanged_code_with_wrong_native_entry_offset_is_rejected(self):
        def mutate(raw,row):
            symbol='boom_m'+str(row['metadata']['source']['methods'][0]['method'])
            at=exported_symbol(raw,symbol);old=struct.unpack_from('<I',raw,at+8)[0]
            struct.pack_into('<I',raw,at+8,old+1)
        for kind in self.paths:
            with self.subTest(kind=kind):self.mutated(kind,mutate)

    def test_unchanged_code_with_wrong_native_symbol_type_is_rejected(self):
        def mutate(raw,row):
            symbol='boom_m'+str(row['metadata']['source']['methods'][0]['method'])
            at=exported_symbol(raw,symbol);old=struct.unpack_from('<H',raw,at+14)[0]
            struct.pack_into('<H',raw,at+14,old^0x20)
        for kind in self.paths:
            with self.subTest(kind=kind):self.mutated(kind,mutate)

    def test_unchanged_instructions_with_writable_code_flag_is_rejected(self):
        def mutate(raw,row):
            try:at=section(raw,'.text$mn')
            except StopIteration:at=section(raw,'.text')
            flags=struct.unpack_from('<I',raw,at+36)[0];struct.pack_into('<I',raw,at+36,flags^0x80000000)
        for kind in self.paths:
            with self.subTest(kind=kind):self.mutated(kind,mutate)

    def test_unchanged_instructions_with_wrong_unwind_is_rejected(self):
        def mutate(raw,row):
            at=section(raw,'.xdata');offset=struct.unpack_from('<I',raw,at+20)[0];raw[offset]^=1
        for kind in self.paths:
            with self.subTest(kind=kind):self.mutated(kind,mutate)


if __name__=='__main__':unittest.main()
