"""Real ml64/link fixtures for optional parallel diagnostic object consumers."""
import copy
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


D=module('diagnostic_objects_test_consumer','diagnostic-objects.py')
B=module('diagnostic_objects_test_original_ranges','batch-source.py')
C=module('diagnostic_objects_test_original_coff','verify-batch-assembly.py')
V=module('diagnostic_objects_test_image_link','verify-diagnostic-closure.py')
N=module('diagnostic_objects_test_native_link','verify-vm-entry.py')
R=module('diagnostic_objects_test_canonical_link','canonical-link-response.py')
ML64=Path(os.environ.get('BOOM_TEST_ML64','D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe'))
SOURCE='''option casemap:none
.data?
PUBLIC boom_probe_static_roots
boom_probe_static_roots LABEL QWORD
boom_root_one QWORD ?
boom_root_two QWORD ?
.data
boom_private QWORD 41
PUBLIC boom_flag
boom_flag DWORD 0
.const
PUBLIC boom_probe_static_root_count
boom_probe_static_root_count QWORD 2
.code
PUBLIC boom_first
PUBLIC boom_second
boom_first PROC FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 call boom_second
 add rax,QWORD PTR [boom_private]
 add rsp,40
 ret
boom_first ENDP
boom_second PROC FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 mov eax,42
 add rsp,40
 ret
boom_second ENDP
END
'''
STOPS='''option casemap:none
.code
PUBLIC boom_stop
boom_stop PROC
 mov eax,7
 ret
boom_stop ENDP
END
'''


class DiagnosticObjectConsumers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name!='nt' or not ML64.is_file():raise unittest.SkipTest('Real Windows ml64/link tools required')
        cls.root=ROOT/'.boom/diagnostic-object-tests'/uuid4().hex
        cls.root.mkdir(parents=True)
        runtime=cls.root/'runtime';runtime.mkdir()
        asm=runtime/'runtime.asm';obj=runtime/'runtime.obj';cls.runtime=runtime/'boom-runtime.dll'
        asm.write_text('option casemap:none\n.code\nPUBLIC boom_fixture_runtime\nboom_fixture_runtime PROC\n ret\nboom_fixture_runtime ENDP\nEND\n',encoding='utf-8')
        for command in ([str(ML64),'/nologo','/c','/Fo'+str(obj),str(asm)],
                        [str(ML64.with_name('link.exe')),'/NOLOGO','/DLL','/NOENTRY','/OUT:'+str(cls.runtime),str(obj),'/EXPORT:boom_fixture_runtime']):
            result=subprocess.run(command,capture_output=True)
            if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        cls.libraries=R.diagnostic_libraries(cls.runtime)[0]

    def setUp(self):
        self.directory=self.root/self.id().split('.')[-1];self.directory.mkdir()
        self.write_source(SOURCE)
        (self.directory/'diagnostic-stops.asm').write_text(STOPS,encoding='utf-8')
        (self.directory/'diagnostic.json').write_text(json.dumps(dict(global_provider_identity=dict(runtime_dll=str(self.runtime)))),encoding='utf-8')

    def write_source(self,text):
        raw=text.encode();(self.directory/'initialization-closure.asm').write_bytes(raw)
        hashes={n:hashlib.sha256(raw[a:b].replace(b'\r\n',b'\n')).hexdigest() for n,(a,b) in B.procedure_spans(raw).items()}
        self.manifest=dict(selected_function_sha256=hashes,objects=[],exports=['boom_first','boom_stop'])
        (self.directory/'closure.json').write_text(json.dumps(self.manifest),encoding='utf-8')

    def parallel(self):
        D.assemble(self.directory,ML64,parallel_assembly=True,workers=2,code_mib=1)
        return D.verify(self.directory)

    def rewrite_receipt(self,change):
        path=self.directory/D.RECEIPT;value=json.loads(path.read_bytes());change(value)
        path.write_text(json.dumps(value),encoding='utf-8')

    def link(self,sealed):
        rsp=['/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT','/BREPRO',
             '/OUT:"'+str(self.directory/'diagnostic-image.dll')+'"']
        rsp+=['"'+u['object']['path']+'"' for u in sealed['units']]
        rsp+=['"'+str(path)+'"' for path in self.libraries]
        rsp+=['/EXPORT:'+s for s in self.manifest['exports']]
        path=self.directory/'link.rsp';path.write_text('\n'.join(rsp)+'\n',encoding='utf-8')
        result=subprocess.run([str(ML64.with_name('link.exe')),'@'+str(path)],capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return path

    def test_default_schema1_and_real_parallel_link_execute_same_source_result(self):
        default=self.directory/'legacy';default.mkdir()
        for name in ('initialization-closure.asm','diagnostic-stops.asm','closure.json'):
            (default/name).write_bytes((self.directory/name).read_bytes())
        D.assemble(default,ML64)
        with patch.object(D,'module',side_effect=AssertionError('Legacy receipt must not need the fresh splitter')):
            old=D.verify(default)
        self.assertEqual(set(old),{'receipt_sha256','assembler','units'})
        self.assertEqual(json.loads((default/D.RECEIPT).read_bytes())['schema'],1)
        sealed=self.parallel();self.link(sealed)
        self.assertEqual(sealed,D.verify(self.directory))
        self.assertFalse((self.directory/'initialization-closure.obj').exists())
        self.assertEqual(len(sealed['units']),3)
        self.assertFalse(sealed['monolithic_reference_used'])
        self.assertFalse(sealed['monolithic_binary_equivalence'])
        proof=sealed['parallel_source_proof']
        self.assertTrue(proof['source_byte_preservation_verified'] and proof['actual_COFF_verified'])
        self.assertEqual((proof['source_functions'],proof['framed_functions'],proof['static_roots']['cells']),(2,2,2))
        expected=C.coff_symbols(default/'initialization-closure.obj')
        self.assertEqual(D.logical_symbols(self.directory,'initialization-closure',C.coff_symbols),expected)
        self.assertEqual(D.logical_symbols(self.directory,'diagnostic-stops',C.coff_symbols),({'boom_stop'},set()))
        self.assertEqual(sealed['logical_units'][0]['promoted_data'],['boom_private','boom_root_one','boom_root_two'])
        V.verify_parallel_link(self.directory,self.manifest,sealed)
        dll=ctypes.CDLL(str(self.directory/'diagnostic-image.dll'))
        dll.boom_first.restype=ctypes.c_uint64;dll.boom_stop.restype=ctypes.c_uint64
        self.assertEqual((dll.boom_first(),dll.boom_stop()),(83,7))

    def test_part_machine_bytes_cannot_change_after_sealing(self):
        sealed=self.parallel();obj=Path(sealed['units'][1]['object']['path'])
        raw=bytearray(obj.read_bytes());raw[-1]^=1;obj.write_bytes(raw)
        with self.assertRaisesRegex(ValueError,'part changed'):D.verify(self.directory)

    def test_complete_source_change_is_rejected(self):
        self.parallel();path=self.directory/'initialization-closure.asm'
        path.write_bytes(path.read_bytes().replace(b'eax,42',b'eax,43'))
        with self.assertRaisesRegex(ValueError,'full source changed'):D.verify(self.directory)

    def test_partial_missing_or_reordered_part_inventory_is_rejected(self):
        self.parallel();path=self.directory/D.RECEIPT;saved=path.read_bytes()
        for change in (lambda r:r['units'][0]['parts'].pop(),lambda r:r['units'][0]['parts'].reverse()):
            path.write_bytes(saved);self.rewrite_receipt(change)
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'coverage differs'):D.verify(self.directory)

    def test_original_public_function_cannot_be_hidden_as_data_promotion(self):
        sealed=self.parallel()
        forged=copy.deepcopy(sealed);forged['logical_units'][0]['promoted_data'].append('boom_first')
        forged['logical_units'][0]['promoted_data'].sort()
        with patch.object(D,'verify',return_value=forged):
            with self.assertRaisesRegex(ValueError,'extra function|original public'):D.logical_symbols(self.directory,'initialization-closure',C.coff_symbols)

    def test_private_source_proc_is_rejected_before_assembly(self):
        self.write_source(SOURCE.replace('PUBLIC boom_second\n',''))
        with self.assertRaisesRegex(ValueError,'Private procedures'):self.parallel()
        self.assertFalse((self.directory/D.RECEIPT).exists())

    def test_unresolved_native_import_is_preserved(self):
        self.write_source(SOURCE.replace('.data?','EXTERN boom_missing_native:PROC\n.data?',1).replace('call boom_second','call boom_missing_native\n call boom_second'))
        self.parallel()
        self.assertEqual(D.logical_symbols(self.directory,'initialization-closure',C.coff_symbols)[1],{'boom_missing_native'})

    def test_actual_foreign_import_is_rejected_by_original_coff_reader(self):
        sealed=self.parallel();extra=self.directory/'foreign.asm';obj=extra.with_suffix('.obj')
        extra.write_text('option casemap:none\nEXTERN GetTickCount64:PROC\n.code\nPUBLIC boom_foreign\nboom_foreign PROC\n jmp GetTickCount64\nboom_foreign ENDP\nEND\n',encoding='utf-8')
        result=subprocess.run([str(ML64),'/nologo','/c','/Fo'+str(obj),str(extra)],capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        forged=copy.deepcopy(sealed);forged['logical_units'][0]['parts'].append(dict(assembly=D.artifact(extra),object=D.artifact(obj)))
        with patch.object(D,'verify',return_value=forged):
            with self.assertRaisesRegex(ValueError,'foreign runtime'):D.logical_symbols(self.directory,'initialization-closure',C.coff_symbols)

    def test_real_link_requires_all_sealed_parts_in_order_and_hides_promotions(self):
        sealed=self.parallel();path=self.link(sealed);original=path.read_text(encoding='utf-8')
        lines=original.splitlines();indexes=[i for i,line in enumerate(lines) if line.endswith('.obj"')]
        lines[indexes[0]],lines[indexes[1]]=lines[indexes[1]],lines[indexes[0]]
        path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'parts or their order'):V.verify_parallel_link(self.directory,self.manifest,sealed)
        path.write_text(original+'/FORCE:MULTIPLE\n',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Canonical LINK response'):V.verify_parallel_link(self.directory,self.manifest,sealed)
        path.write_text(original,encoding='utf-8')
        wrong=copy.deepcopy(self.manifest);wrong['exports'].append('boom_private')
        with self.assertRaisesRegex(ValueError,'promoted internal data'):V.verify_parallel_link(self.directory,wrong,sealed)

    def test_real_link_input_and_option_bypasses_are_rejected_for_both_images(self):
        sealed=self.parallel();path=self.link(sealed)
        extra=self.directory/'unsealed-extra.asm';obj=extra.with_suffix('.obj');lib=extra.with_suffix('.lib')
        extra.write_text('option casemap:none\n.code\nPUBLIC boom_unsealed_extra\nboom_unsealed_extra PROC\n mov eax,123\n ret\nboom_unsealed_extra ENDP\nEND\n',encoding='utf-8')
        for command in ([str(ML64),'/nologo','/c','/Fo'+str(obj),str(extra)],
                        [str(ML64.with_name('lib.exe')),'/NOLOGO','/OUT:'+str(lib),str(obj)]):
            result=subprocess.run(command,capture_output=True);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        nested=self.directory/'nested.rsp';nested.write_text('"'+str(obj)+'"\n',encoding='utf-8')
        native_asm=self.directory/'vm-entry.asm';native_obj=native_asm.with_suffix('.obj')
        native_asm.write_text('option casemap:none\nEXTERN ExitProcess:PROC\n.code\nPUBLIC boom_process_entry\nboom_process_entry PROC\n xor ecx,ecx\n jmp ExitProcess\nboom_process_entry ENDP\nEND\n',encoding='utf-8')
        result=subprocess.run([str(ML64),'/nologo','/c','/Fo'+str(native_obj),str(native_asm)],capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        native_rsp=['/NOLOGO','/MACHINE:X64','/SUBSYSTEM:CONSOLE','/ENTRY:boom_process_entry','/NODEFAULTLIB',
                    '/DYNAMICBASE','/NXCOMPAT','/HIGHENTROPYVA','/BREPRO','/STACK:8388608',
                    '/OUT:"'+str(self.directory/'boom-vm-entry.exe')+'"']
        native_rsp+=['"'+u['object']['path']+'"' for u in sealed['units']]+['"'+str(native_obj)+'"']
        native_rsp+=['"'+str(p)+'"' for p in self.libraries]+['/EXPORT:boom_process_entry']
        native_manifest=dict(reassembled_objects=[D.artifact(native_obj)],inputs=[D.artifact(p) for p in [Path(R.__file__),*self.libraries]],
            executable=dict(path=str(self.directory/'boom-vm-entry.exe')))
        records=[]
        for profile,original in (('diagnostic',path.read_text(encoding='utf-8')),('native','\n'.join(native_rsp)+'\n')):
            def verify():
                if profile=='diagnostic':return V.verify_parallel_link(self.directory,self.manifest,sealed)
                native_manifest['link_response']=D.artifact(path)
                return N.verify_link(native_manifest,self.runtime,{'boom_process_entry'},
                    [u['object']['path'] for u in sealed['units']]+[str(native_obj)],sealed)
            lines=original.splitlines();indices=[i for i,line in enumerate(lines) if line.endswith('.obj"')]
            swapped=lines.copy();swapped[indices[0]],swapped[indices[1]]=swapped[indices[1]],swapped[indices[0]]
            unquoted=lines.copy();unquoted[indices[0]]=unquoted[indices[0]][1:-1]
            cases=dict(leading_space_object=original+' \t"'+str(obj)+'"\n',unquoted_object=original+str(obj)+'\n',
                unquoted_sealed_object='\n'.join(unquoted)+'\n',nested_response=original+'@"'+str(nested)+'"\n',
                whole_archive_library=original+'/WHOLEARCHIVE:"'+str(lib)+'"\n',
                whole_archive_object=original+'/WHOLEARCHIVE:"'+str(obj)+'"\n',
                leading_space_force=original+' \t/FORCE:MULTIPLE\n',force=original+'/FORCE:MULTIPLE\n',
                duplicate_object=original+lines[indices[0]]+'\n',reordered_objects='\n'.join(swapped)+'\n',
                duplicate_output=original+next(line for line in lines if line.startswith('/OUT:'))+'\n',
                duplicate_export=original+next(line for line in lines if line.startswith('/EXPORT:'))+'\n',
                extra_library=original+'"'+str(lib)+'"\n')
            for name,response in [('canonical',original),*cases.items()]:
                with self.subTest(profile=profile,form=name):
                    path.write_text(response,encoding='utf-8')
                    result=subprocess.run([str(ML64.with_name('link.exe')),'@'+str(path)],capture_output=True)
                    (self.directory/(profile+'-'+name+'-link.log')).write_bytes(result.stdout+result.stderr)
                    if name=='canonical':
                        self.assertEqual(result.returncode,0,result.stdout+result.stderr);verify()
                    else:
                        if name not in {'nested_response','whole_archive_object'}:self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                        with self.assertRaisesRegex(ValueError,'Canonical LINK response'):verify()
                    records.append(dict(profile=profile,form=name,actual_LINK_exit=result.returncode,rejected=name!='canonical'))
        (self.directory/'actual-link-negative-results.json').write_text(json.dumps(records,indent=2),encoding='utf-8')

    def test_real_link_cannot_export_internal_promoted_data(self):
        sealed=self.parallel();self.manifest['exports'].append('boom_private')
        self.link(sealed)
        self.assertIn('boom_private',V.load('promoted_export_fixture','diagnostic-closure.py').pe_exports(self.directory/'diagnostic-image.dll'))
        with self.assertRaisesRegex(ValueError,'promoted internal data'):V.verify_parallel_link(self.directory,self.manifest,sealed)

    def test_native_link_requires_helper_pin_and_unique_reassembled_names(self):
        sealed=self.parallel();path=self.link(sealed)
        obj=sealed['units'][1]['object'];manifest=dict(reassembled_objects=[obj],inputs=[],link_response=D.artifact(path),
            executable=dict(path=str(self.directory/'boom-vm-entry.exe')))
        with self.assertRaisesRegex(ValueError,'canonical LINK verifier source'):
            N.verify_link(manifest,self.runtime,set(),[obj['path']],sealed)
        manifest['reassembled_objects'].append(obj)
        with self.assertRaisesRegex(ValueError,'duplicate assembly object names'):
            N.verify_link(manifest,self.runtime,set(),[obj['path']],sealed)


if __name__=='__main__':unittest.main()
