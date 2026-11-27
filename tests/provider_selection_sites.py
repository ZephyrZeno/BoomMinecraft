"""Only selected original Java Code receives a callable native table entry."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import struct
import subprocess
from types import SimpleNamespace
import unittest
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
ASM=Path('D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe')

def module(name):
    spec=importlib.util.spec_from_file_location('test_selection_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

P=module('provider-selection-sites');C=module('method-invoke-source')

def record(method,owner,**extra):
    value=dict(method=method,owner=owner,available=True,caller_sensitive=False,assembly_emitted=True,frame_flags=0,
        source_sha256='a'*64,code_sha256='b'*64);value.update(extra);return value

def selected(r):
    return dict(class_id=r['owner'],source_sha256=r['source_sha256'],code_sha256=r['code_sha256'])

def metadata():
    return dict(selection_specific_sites_required=True,selected_site_bytes=32,
        records=[record(10,1),record(20,1),record(30,2),record(40,2,available=False,caller_sensitive=True)])

def project(meta,classes,methods,indices=(0,)):
    path={'path':'fixture-metadata.json','digest':{'sha256':'fixture'}}
    family='normal-method-invoke-static-v1'
    packs=[dict(manifest=dict(family=family,method_invoke_metadata=path),reference={'path':'fixture-provider.json'})]
    def load(name,file):
        if file=='framed-runtime-service.py':return SimpleNamespace(FAMILIES={family:('method-invoke-source.py','method_invoke','unused')})
        if file=='method-invoke-source.py':return C
        raise AssertionError(file)
    def check(value,message):
        if not value:raise ValueError(message)
    S=SimpleNamespace(module=load,checked=lambda r:r['path'],read=lambda path:meta,check=check)
    return P.project(packs,set(indices),classes,methods,S)


class NativeSelection(unittest.TestCase):
    def test_ready_target_and_original_class_and_method_gaps(self):
        meta=metadata();classes={1};methods={10:selected(meta['records'][0])}
        text,pending_methods,pending_classes,proof=project(meta,classes,methods)
        self.assertEqual(pending_methods,{20});self.assertEqual(pending_classes,{2})
        self.assertEqual([r['ready'] for r in proof[0]['sites']],[True,False,False,False])
        self.assertEqual([r['callback'] for r in proof[0]['sites']],[None,'boom_m20','boom_batch_initialize_2',None])
        self.assertEqual(proof[0]['sites'][3]['reason'],'caller_sensitive_unsupported')
        self.assertEqual(classes,{1});self.assertEqual(set(methods),{10})
        self.assertIn('QWORD OFFSET boom_class1,OFFSET boom_m10,0,0',text)
        self.assertIn('QWORD OFFSET boom_class1,0,OFFSET boom_m20,0',text)
        self.assertIn('QWORD 0,0,OFFSET boom_batch_initialize_2,0',text)
        self.assertIn('QWORD 0,0,0,0',text)

    def test_unselected_pack_has_no_table_and_no_admissions(self):
        self.assertEqual(project(metadata(),set(),{},indices=()),('',set(),set(),[]))

    def test_selected_Code_provenance_and_ABI_are_not_optional(self):
        meta=metadata();good=selected(meta['records'][0])
        for changed in (dict(good,class_id=2),dict(good,code_sha256='c'*64),dict(good,source_sha256='d'*64)):
            with self.subTest(changed=changed),self.assertRaises(ValueError):project(meta,{1},{10:changed})
        for key,value in (('assembly_emitted',False),('frame_flags',128)):
            bad=deepcopy(meta);bad['records'][0][key]=value
            with self.assertRaises(ValueError):project(bad,{1},{10:good})
        bad=dict(meta,selected_site_bytes=24)
        with self.assertRaises(ValueError):project(bad,{1},{10:good})

    def test_all_normal_targets_selected_has_no_diagnostic_callbacks(self):
        meta=metadata();methods={r['method']:selected(r) for r in meta['records'] if r['available']}
        _,pending_methods,pending_classes,proof=project(meta,{1,2},methods)
        self.assertEqual((pending_methods,pending_classes),(set(),set()))
        self.assertEqual([r['ready'] for r in proof[0]['sites']],[True,True,True,False])

    @unittest.skipUnless(ASM.is_file(),'MSVC ml64 required for physical selected table test')
    def test_actual_readonly_table_has_only_expected_source_relocations(self):
        meta=metadata();text,imports,sites=C.selected_sites(meta,{1},{10:selected(meta['records'][0])})
        directory=ROOT/'.boom/provider-selection-tests'/uuid4().hex;directory.mkdir(parents=True)
        asm,obj=directory/'selected.asm',directory/'selected.obj'
        asm.write_text('option casemap:none\n'+''.join('EXTERN '+n+':BYTE\n' for n in sorted(imports))+text+'END\n')
        subprocess.run([str(ASM),'/nologo','/c','/Fo'+str(obj),str(asm)],check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        coff=module('verify-batch-assembly');self.assertEqual(coff.coff_symbols(obj),(set([C.SELECTED]),imports))
        raw=obj.read_bytes();count=struct.unpack_from('<H',raw,2)[0];found=[]
        for i in range(count):
            at=20+40*i
            if raw[at:at+8].rstrip(b'\0')==b'.rdata':
                size,data,relocs=struct.unpack_from('<III',raw,at+16);number=struct.unpack_from('<H',raw,at+32)[0]
                flags=struct.unpack_from('<I',raw,at+36)[0]
                self.assertFalse(flags&0xA0000020);self.assertTrue(flags&0x40000040)
                self.assertEqual(size,len(sites)*32);self.assertFalse(any(raw[data:data+size]))
                found=[struct.unpack_from('<IIH',raw,relocs+10*j) for j in range(number)]
        self.assertEqual([(r[0],r[2]) for r in found],[(0,1),(8,1),(32,1),(48,1),(80,1)])


if __name__=='__main__':unittest.main()
