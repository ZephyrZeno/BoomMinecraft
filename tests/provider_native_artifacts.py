"""Formal provider projection, readonly data and real native COFF guards."""
import ast
from contextlib import nullcontext
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
ASM=Path('D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe')

def module(name):
    spec=importlib.util.spec_from_file_location('test_provider_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

A=module('provider-native-artifacts')
S=module('runtime-provider-source')

def row(ident=8,owner=0,**extra):
    return dict(method=ident,class_id=owner,class_sha256=str(owner)*64,loader='bootstrap',owner=('Class' if owner==0 else 'CP'),
        source_id='jdk:java.base',name='native'+str(ident),descriptor='()V',access=0x102,operation=ident,**extra)

def source_classes():
    return [dict(id=i,name=n,origin=dict(sha256=str(i)*64,loader='bootstrap',source_id='jdk:java.base'))
        for i,n in enumerate(('Class','CP'))]

def rule(rows):
    return dict(owner='Class',loader='bootstrap',source_id='jdk:java.base',native_java_upcalls=True,
        methods=[{k:r[k] for k in ('owner','name','descriptor','access','operation')} for r in rows])

def fresh():
    path=ROOT/'.boom/provider-native-artifacts-tests'/uuid4().hex;path.mkdir(parents=True);return path

def toy_rom():
    C=module('normal-constant-pool-source');payload=bytes(range(64))
    meta=dict(readonly_section_bytes=len(payload),readonly_section_sha256=hashlib.sha256(payload).hexdigest(),
        entry_section_offset=24,raw_section_offset=40)
    return C,C.rom_coff(payload,meta),meta


class NativeProjection(unittest.TestCase):
    def test_native_Code_None_is_the_only_optional_projection(self):
        native=row(code_sha256=None);self.assertEqual(A.methods(dict(methods=[native])),[row()])
        for changed in (dict(native,code_sha256='ab'*32),dict(native,unknown=True),dict(native,access=0x2),
                        dict(native,access=0x502)):
            with self.subTest(changed=changed),self.assertRaises(ValueError):A.methods(dict(methods=[changed]))
        with self.assertRaises(ValueError):A.methods(dict(methods=[row(),row()]))

    def test_multiowner_without_optional_primary_owner(self):
        rows=[row(),row(9,1)];classes=source_classes();primary,all_=A.owners(dict(methods=rows),classes,rule(rows))
        self.assertEqual(primary,classes[0]);self.assertEqual(all_,classes)
        self.assertEqual(A.owners(dict(owner=0,methods=rows),classes,rule(rows)),(primary,all_))
        for meta in (dict(owner=1,methods=rows),dict(methods=[rows[0],dict(rows[1],loader='application')]),
                     dict(methods=[rows[0],dict(rows[1],operation=100)])):
            with self.subTest(meta=meta),self.assertRaises(ValueError):A.owners(meta,classes,rule(rows))
        classes[1]['origin']['sha256']='wrong'
        with self.assertRaises(ValueError):A.owners(dict(methods=rows),classes,rule(rows))

    def test_callbacks_and_registry_dependency_supplement_preserve_source(self):
        meta=dict(required_java_methods=[92,14],required_provider_families=['normal-throwable-v1'],
            required_source_contracts=['boom_batch_call_1_2_3'])
        r=dict(native_java_upcalls=True,required_provider_families=['normal-methods-v1','normal-throwable-v1'])
        expected=dict(required_java_methods=[92,14],required_provider_families=['normal-throwable-v1','normal-methods-v1'],
            required_source_contracts=['boom_batch_call_1_2_3'],native_java_upcalls=True)
        self.assertEqual(A.dependencies(meta,r),expected);self.assertEqual(meta['required_provider_families'],['normal-throwable-v1'])
        for bad in (dict(meta,required_java_methods=[14,14]),dict(meta,required_source_contracts=['host_target']),
                    dict(meta,required_provider_families=['same','same'])):
            with self.assertRaises(ValueError):A.dependencies(bad,r)
        with self.assertRaises(ValueError):A.dependencies(meta,{})


class ReadonlySourceObjects(unittest.TestCase):
    def test_exact_data_flags_exports_and_original_payload(self):
        C,raw,meta=toy_rom();p=fresh()/'ROM.obj';p.write_bytes(raw)
        proof=A.verify_readonly(p,raw,C.ROM_EXPORTS)
        self.assertTrue(proof['readonly']);self.assertEqual(proof['relocations'],0);self.assertFalse(proof['code_sections'])
        self.assertEqual(proof['payload_sha256'],meta['readonly_section_sha256'])
        for offset,value in ((56,0xC0500040),(56,0x60500020),(44,8),(52,1)):
            bad=bytearray(raw);struct.pack_into('<I',bad,offset,value);p.write_bytes(bad)
            with self.subTest(offset=offset,value=value),self.assertRaises(ValueError):A.verify_readonly(p,bytes(bad),C.ROM_EXPORTS)
        p.write_bytes(raw)
        with self.assertRaises(ValueError):A.verify_readonly(p,raw,C.ROM_EXPORTS|{'foreign_definition'})
        bad=bytearray(raw);bad[64]^=1;p.write_bytes(bad)
        with self.assertRaises(ValueError):A.verify_readonly(p,raw,C.ROM_EXPORTS)

    def test_ROM_alias_complete_order_and_duplicate_guard(self):
        p=fresh();code=dict(path=str(p/'code.obj'),digest={});rom=dict(path=str(p/'ROM.obj'),digest={})
        extra=dict(role='source_constant_pool_ROM',object=rom,exports=['one'],source_payload_sha256='a'*64,read_only_source_metadata=True)
        manifest=dict(family='normal-constant-pool-v1',object=code,additional_objects=[extra],ROM_object=rom)
        self.assertEqual(A.object_records(manifest),[code,rom])
        for bad in (dict(manifest,ROM_object=code),{k:v for k,v in manifest.items() if k!='ROM_object'},
                    dict(manifest,additional_objects=[extra,extra]),
                    dict(manifest,additional_objects=[dict(extra,read_only_source_metadata=False)]),
                    dict(manifest,additional_objects=[dict(extra,role='executable')]),
                    dict(manifest,family='normal-throwable-v1')):
            with self.subTest(bad=bad),self.assertRaises(ValueError):A.object_records(bad)

    def test_cache_copies_ROM_but_never_publishes_on_current_verifier_failure(self):
        R=module('revalidate-runtime-provider-cache');p=fresh();source=p/'producer';source.mkdir()
        C,raw,meta=toy_rom();(source/'provider.asm').write_text('; source fixture\n');(source/'provider.obj').write_bytes(b'fixture code')
        (source/'ROM.obj').write_bytes(raw)
        extra=dict(role='source_constant_pool_ROM',object=R.S.artifact(source/'ROM.obj'),exports=sorted(C.ROM_EXPORTS),
            source_payload_sha256=meta['readonly_section_sha256'],read_only_source_metadata=True)
        m=dict(family='normal-constant-pool-v1',assembly=R.S.artifact(source/'provider.asm'),object=R.S.artifact(source/'provider.obj'),
            additional_objects=[extra],ROM_object=extra['object'],tool_sources={'fixture':True})
        R.S.write(source/'provider.json',m)
        R.S.write(source/'verification.json',dict(verified=True,provider_manifest_sha256=R.S.digest(source/'provider.json')['sha256'],test_fixture_only=True))
        frame=p/'frame';frame.mkdir();R.S.write(frame/'overlay.json',{'test_fixture_only':True});R.S.write(frame/'verification.json',{'test_fixture_only':True})
        target=R.S.ART/'runtime-providers'/('fixture-reject-'+uuid4().hex)
        def reject(manifest,batch,plan):
            copied=R.S.read(manifest);records=A.object_records(copied)
            self.assertEqual([Path(r['path']).parent for r in records],[Path(manifest).parent]*2)
            self.assertEqual(R.S.checked(records[1]).read_bytes(),raw)
            A.verify_readonly(R.S.checked(records[1]),raw,C.ROM_EXPORTS)
            self.assertFalse(copied['native_ASM_codegen_rerun']);self.assertFalse(copied['COFF_reassembled_this_build'])
            raise ValueError('intentional current verification failure in test fixture')
        verifier=SimpleNamespace(S=SimpleNamespace(base_scope=lambda *args:nullcontext()),verify=reject)
        with patch.object(R.S,'module',return_value=verifier),patch.object(R.S,'tools_identity',return_value={'test':True}):
            with self.assertRaisesRegex(ValueError,'intentional current verification failure'):
                R.refresh_packs([source/'provider.json'],p,p,frame/'overlay.json',target)
        self.assertFalse((target/'accepted-caches.json').exists())
        self.assertFalse((target/m['family']/'verification.json').exists())
        self.assertEqual((source/'ROM.obj').read_bytes(),raw)


@unittest.skipUnless(ASM.is_file(),'MSVC ml64 required for real COFF guards')
class CompleteMachineContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=fresh();cls.asm=cls.directory/'actual.asm';cls.obj=cls.directory/'actual.obj'
        cls.text='''option casemap:none
EXTERN source_target:PROC
.data
ALIGN 8
PUBLIC fixture_pool
fixture_pool QWORD OFFSET source_target
.code
PUBLIC fixture_entry
fixture_entry PROC FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 call source_target
 add rsp,40
 ret
fixture_entry ENDP
END
'''
        cls.asm.write_text(cls.text)
        subprocess.run([str(ASM),'/nologo','/c','/Fo'+str(cls.obj),str(cls.asm)],check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        cls.raw=cls.obj.read_bytes();cls.normal=A.normalized_coff(cls.obj)

    def test_fresh_reassembly_and_complete_section_contract(self):
        proof=A.machine_contract(self.text,self.obj,ASM,S)
        self.assertTrue(proof['all_nondebug_sections_symbols_auxiliary_relocations_unwind_verified'])
        self.assertTrue({'.data','.pdata','.xdata'}<=set(self.normal['sections']))
        self.assertTrue({'.text','.text$mn'}&set(self.normal['sections']))

    def test_execution_bytes_section_flags_auxiliary_and_relocation_changes(self):
        raw=self.raw;count=struct.unpack_from('<H',raw,2)[0];sections={}
        for i in range(count):
            at=20+i*40;sections[raw[at:at+8].rstrip(b'\0').decode()]=(at,struct.unpack_from('<IIIIIIHHI',raw,at+8))
        modifications=[];text_at,t=sections['.text' if '.text' in sections else '.text$mn'];modifications.append((t[3],1,1))
        modifications.append((text_at+36,4,t[-1]^0x80000000))
        # The relocation target index is part of the normalized contract.
        data_at,data=sections['.data'];reloc=data[4];modifications.append((reloc+8,2,2))
        symbol_at,symbol_count=struct.unpack_from('<II',raw,8);index=0;aux_offset=None
        while index<symbol_count:
            aux=raw[symbol_at+index*18+17]
            name=raw[symbol_at+index*18:symbol_at+index*18+8].rstrip(b'\0')
            storage=raw[symbol_at+index*18+16]
            if aux and storage!=103 and name!=b'.debug$S':aux_offset=symbol_at+(index+1)*18;break
            index+=1+aux
        self.assertIsNotNone(aux_offset);modifications.append((aux_offset,1,raw[aux_offset]^1))
        for n,(offset,width,value) in enumerate(modifications):
            changed=bytearray(raw)
            if n==0:changed[offset]^=value
            else:struct.pack_into({1:'<B',2:'<H',4:'<I'}[width],changed,offset,value)
            p=self.directory/f'changed-{n}.obj';p.write_bytes(changed)
            with self.subTest(change=n):
                try:normalized=A.normalized_coff(p)
                except ValueError:continue
                self.assertNotEqual(normalized,self.normal)
        bad=self.directory/'changed-0.obj'
        with self.assertRaisesRegex(ValueError,'differ from canonical assembly'):A.machine_contract(self.text,bad,ASM,S)

    def test_missing_or_truncated_unwind_is_rejected(self):
        raw=bytearray(self.raw);count=struct.unpack_from('<H',raw,2)[0]
        for i in range(count):
            at=20+i*40
            if raw[at:at+8].rstrip(b'\0')==b'.pdata':struct.pack_into('<I',raw,at+16,11);break
        p=self.directory/'bad-unwind.obj';p.write_bytes(raw)
        with self.assertRaises(ValueError):A.normalized_coff(p)


if __name__=='__main__':unittest.main()
