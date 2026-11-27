"""Readonly source COFF travels through normal VM inputs and strict LINK order."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
ASM=Path('D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe')
LINK=ASM.with_name('link.exe')

def module(name):
    spec=importlib.util.spec_from_file_location('test_readonly_'+name,ROOT/'scripts'/(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

S=module('runtime-provider-source');A=module('provider-native-artifacts');C=module('normal-constant-pool-source')

def inputs():
    p=ROOT/'.boom/provider-readonly-link-tests'/uuid4().hex;p.mkdir(parents=True)
    payload=bytes(range(64));rom_meta=dict(readonly_section_bytes=64,readonly_section_sha256=hashlib.sha256(payload).hexdigest(),
        entry_section_offset=24,raw_section_offset=40)
    data=p/'readonly.obj';data.write_bytes(C.rom_coff(payload,rom_meta));code=p/'code.obj';code.write_bytes(b'source object fixture')
    extra=dict(role='source_constant_pool_ROM',object=S.artifact(data),exports=sorted(C.ROM_EXPORTS),
        source_payload_sha256=rom_meta['readonly_section_sha256'],read_only_source_metadata=True)
    pack=dict(family='normal-constant-pool-v1',object=S.artifact(code),additional_objects=[extra],ROM_object=extra['object'])
    S.write(p/'provider.json',pack);batch=p/'batch';batch.mkdir();S.write(batch/'summary.json',{})
    closure=dict(batch=str(batch),runtime_provider_packs=[dict(manifest=S.artifact(p/'provider.json'))],
        objects=[r['path'] for r in A.object_records(pack)])
    return p,pack,closure


class NativeInputChain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Exercise the unchanged production consumer itself, isolated from its
        # expensive unrelated global imports and binding-model initialization.
        path=ROOT/'scripts/vm-entry-source.py';tree=ast.parse(path.read_text())
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='source_objects')
        scope=dict(Path=Path,S=S)
        exec(compile(ast.Module(body=[function],type_ignores=[]),str(path),'exec'),scope)
        cls.source_objects=staticmethod(scope['source_objects'])

    def test_normal_VM_consumer_seals_both_code_and_readonly_data_in_order(self):
        _,pack,closure=inputs();records=self.source_objects(closure)
        self.assertEqual(records,A.object_records(pack));self.assertEqual(len(records),2)
        self.assertEqual(records[1],pack['ROM_object'])

    def test_unsealed_or_changed_readonly_object_rejected(self):
        p,pack,closure=inputs();data=Path(pack['ROM_object']['path']);data.write_bytes(data.read_bytes()+b'changed')
        with self.assertRaisesRegex(ValueError,'artifact changed'):self.source_objects(closure)
        p,pack,closure=inputs();pack.pop('additional_objects');pack.pop('ROM_object');S.write(p/'provider2.json',pack)
        closure['runtime_provider_packs']=[dict(manifest=S.artifact(p/'provider2.json'))]
        with self.assertRaisesRegex(ValueError,'no source-bound digest'):self.source_objects(closure)

    @unittest.skipUnless(ASM.is_file() and LINK.is_file(),'MSVC native tools required for actual readonly LINK')
    def test_real_link_and_strict_ROM_drop_substitution_and_order_rejection(self):
        p,pack,closure=inputs();asm=p/'code.asm';code=Path(pack['object']['path']);target=p/'linked.dll'
        asm.write_text('''option casemap:none
EXTERN boom_constant_pool_directory:BYTE
.code
PUBLIC boom_readonly_fixture
boom_readonly_fixture PROC
 lea rax,boom_constant_pool_directory
 ret
boom_readonly_fixture ENDP
END
''')
        subprocess.run([str(ASM),'/nologo','/c','/Fo'+str(code),str(asm)],check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        L=module('canonical-link-response')
        # This fixture has no runtime imports; the installed SDK libraries are
        # still real LINK inputs and must match the exact sealed choice/order.
        libraries=L.sdk_libraries()[0];objects=[str(code),pack['ROM_object']['path']]
        exports=sorted(C.ROM_EXPORTS|{'boom_readonly_fixture'})
        arguments=[*L.PREFIXES['diagnostic'],'/OUT:"'+str(target)+'"',
            *['"'+str(n)+'"' for n in objects+libraries],*['/EXPORT:'+n for n in exports]]
        response=p/'link.rsp';response.write_text('\n'.join(arguments)+'\n')
        subprocess.run([str(LINK),'@'+str(response)],check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        self.assertTrue(target.is_file())
        kwargs=dict(profile='diagnostic',output=target,objects=objects,library_choices=[libraries],exports=exports)
        self.assertTrue(L.verify(response,**kwargs)['complete_argument_sequence_verified'])
        quoted='"'+objects[1]+'"';at=arguments.index(quoted)
        changed=[arguments[:at]+arguments[at+1:],
            arguments[:at]+['"'+str(p/'foreign.obj')+'"']+arguments[at+1:],
            arguments[:at-1]+[arguments[at],arguments[at-1]]+arguments[at+1:],
            arguments+['/FORCE:MULTIPLE']]
        for i,lines in enumerate(changed):
            path=p/f'bad-{i}.rsp';path.write_text('\n'.join(lines)+'\n')
            with self.subTest(change=i),self.assertRaises(ValueError):L.verify(path,**kwargs)


if __name__=='__main__':unittest.main()
