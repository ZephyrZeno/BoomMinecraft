"""Real COFF property root spans and compatibility with older source batches."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest
from uuid import uuid4
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('original_property_root_contract',ROOT/'scripts/verify-initialization-closure.py')
V=importlib.util.module_from_spec(spec);spec.loader.exec_module(V)
ML64=Path(os.environ.get('BOOM_TEST_ML64','D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe'))


def symbol(raw,wanted):
    offset,count=struct.unpack_from('<II',raw,8);table=offset+count*18;i=0
    while i<count:
        at=offset+i*18;name,value,section,_,_,aux=struct.unpack_from('<8sIhHBB',raw,at)
        if name[:4]==b'\0'*4:
            begin=table+struct.unpack_from('<I',name,4)[0];name=raw[begin:raw.index(b'\0',begin)]
        else:name=name.rstrip(b'\0')
        if name.decode()==wanted:return at,value,section
        i+=aux+1
    raise ValueError('Missing real fixture COFF symbol: '+wanted)


class OriginalPropertyRoots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name!='nt' or not ML64.is_file():raise unittest.SkipTest('Real Windows ml64 required')
        cls.output=ROOT/'.boom/provider-base-module-tests'/uuid4().hex;cls.output.mkdir(parents=True)
        source=cls.output/'properties.asm'
        source.write_text('option casemap:none\n.data?\nALIGN 8\nPUBLIC boom_java_properties_roots\n'
            'boom_java_properties_roots QWORD ?\nproperty_java_string_roots QWORD 108 DUP(?)\n'
            'property_java_string_states DWORD 54 DUP(?)\n.const\nPUBLIC boom_java_properties_root_count\n'
            'boom_java_properties_root_count QWORD 109\nPUBLIC boom_property_fixture_pool\n'
            'boom_property_fixture_pool QWORD OFFSET property_java_string_roots,OFFSET property_java_string_states\nEND\n',encoding='utf-8')
        cls.obj=source.with_suffix('.obj')
        with (cls.output/'assembler.log').open('wb') as log:
            result=subprocess.run([str(ML64),'/nologo','/c','/Fo'+str(cls.obj),str(source)],stdout=log,stderr=log)
        if result.returncode:raise RuntimeError('Property root fixture assembly failed: '+str(cls.output))
        cls.raw=cls.obj.read_bytes()

    def mutated(self,raw):
        path=self.output/(self.id().split('.')[-1]+'.obj');path.write_bytes(raw);return path

    def test_actual_COFF_preserves_the_complete_contiguous_reference_prefix(self):
        proof=V.verify_property_root_span(self.obj,109,54)
        self.assertEqual((proof['offset'],proof['cells'],proof['bytes'],proof['source_string_roots']),(0,109,872,108))
        self.assertTrue(proof['contiguous_original_span_verified'])
        self.assertFalse(proof['runtime_GC_registration_executed'])

    def test_actual_constant_count_change_is_rejected(self):
        raw=bytearray(self.raw);_,value,section=symbol(raw,'boom_java_properties_root_count')
        position=struct.unpack_from('<I',raw,20+(section-1)*40+20)[0]+value
        struct.pack_into('<Q',raw,position,107)
        with self.assertRaisesRegex(ValueError,'root count differs'):V.verify_property_root_span(self.mutated(raw),109,54)

    def test_private_string_root_start_cannot_leave_the_original_span(self):
        raw=bytearray(self.raw);offset,value,_=symbol(raw,'property_java_string_roots');struct.pack_into('<I',raw,offset+8,value+8)
        with self.assertRaisesRegex(ValueError,'contiguous cell offsets'):V.verify_property_root_span(self.mutated(raw),109,54)

    def test_string_state_cannot_overlap_the_reference_prefix(self):
        raw=bytearray(self.raw);offset,value,_=symbol(raw,'property_java_string_states');struct.pack_into('<I',raw,offset+8,value-8)
        with self.assertRaisesRegex(ValueError,'contiguous cell offsets'):V.verify_property_root_span(self.mutated(raw),109,54)

    def test_whole_bank_cannot_move_with_unchanged_export_names(self):
        raw=bytearray(self.raw);offset,value,_=symbol(raw,'boom_java_properties_roots');struct.pack_into('<I',raw,offset+8,value+8)
        with self.assertRaisesRegex(ValueError,'contiguous cell offsets'):V.verify_property_root_span(self.mutated(raw),109,54)

    def test_old_batch_without_a_properties_module_passes_the_full_verifier(self):
        directory=self.output/'old-no-properties';directory.mkdir();batch=directory/'batch';batch.mkdir()
        (batch/'class-state').mkdir();plan=directory/'plan';plan.mkdir();index=batch/'class-state/index.zip'
        with zipfile.ZipFile(index,'w') as z:z.writestr('classes.jsonl','')
        metadata=dict(path=str(index),digest=dict(size=index.stat().st_size,sha1=hashlib.sha1(index.read_bytes()).hexdigest(),sha256=hashlib.sha256(index.read_bytes()).hexdigest()))
        (batch/'summary.json').write_text(json.dumps(dict(schema=5,input_fingerprint='old-unit-fixture',class_state=dict(index=metadata),shards=[])))
        (plan/'summary.json').write_text(json.dumps(dict(input_fingerprint='old-unit-fixture')))
        manifest=dict(batch=str(batch),plan=str(plan),selected_classes=[],selected_methods={},selected_function_sha256={},objects=[])
        (directory/'closure.json').write_text(json.dumps(manifest));source=directory/'initialization-closure.asm'
        source.write_text('option casemap:none\nPUBLIC boom_probe_static_roots\nPUBLIC boom_probe_static_root_count\n'
            '.data?\nboom_probe_static_roots LABEL QWORD\n.const\nboom_probe_static_root_count QWORD 0\n.code\nEND\n')
        result=subprocess.run([str(ML64),'/nologo','/c','/Fo'+str(source.with_suffix('.obj')),str(source)],capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        proof=V.verify(directory)
        self.assertTrue(proof['verified']);self.assertEqual(proof['source_property_natives'],0)
        self.assertIsNone(proof['source_property_root_span'])


if __name__=='__main__':unittest.main()
