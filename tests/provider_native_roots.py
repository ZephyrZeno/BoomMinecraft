"""Real ml64 COFF mutations and explicit native root snapshot protocol tests."""
import ctypes as c
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('actual_provider_roots',ROOT/'scripts/provider-native-roots.py')
N=importlib.util.module_from_spec(spec);spec.loader.exec_module(N)
ML64=Path(os.environ.get('BOOM_TEST_ML64','D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe'))
DECL=[dict(symbol='boom_fixture_root_a',count=4,kind='test_oop_cells'),dict(symbol='boom_fixture_root_b',count=3,kind='test_oop_cells')]
P,Q,U=c.c_void_p,c.c_uint64,c.c_uint32


def symbol_at(raw,wanted):
    at,count=struct.unpack_from('<II',raw,8);strings=at+count*18;i=0
    while i<count:
        name,value,section,_,_,aux=struct.unpack_from('<8sIhHBB',raw,at+i*18)
        if name[:4]==b'\0'*4:
            start=strings+struct.unpack_from('<I',name,4)[0];name=raw[start:raw.index(b'\0',start)]
        else:name=name.rstrip(b'\0')
        if name.decode()==wanted:return at+i*18,value,section
        i+=1+aux
    raise ValueError('Missing fixture COFF symbol')


class NativeProviderRoots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name!='nt' or not ML64.exists():raise unittest.SkipTest('Windows real ml64 required')
        cls.output=ROOT/'.boom/provider-native-roots/unit-tests'/uuid4().hex;cls.output.mkdir(parents=True)
        cls.asm=cls.output/'roots.asm';cls.obj=cls.asm.with_suffix('.obj')
        body='''option casemap:none
.data
ALIGN 8
PUBLIC boom_fixture_root_a
boom_fixture_root_a QWORD 4 DUP(0)
PUBLIC boom_fixture_root_b
boom_fixture_root_b QWORD 3 DUP(0)
PUBLIC boom_fixture_scalar
boom_fixture_scalar QWORD 0
.const
PUBLIC boom_fixture_metadata
boom_fixture_metadata QWORD OFFSET boom_fixture_root_a,4,OFFSET boom_fixture_root_b,3
.data?
PUBLIC boom_fixture_bss
boom_fixture_bss QWORD 2 DUP(?)
'''
        cls.asm.write_text(body+(ROOT/'native/kernels/provider_native_root_snapshot.asm.inc').read_text()+'\nEND\n')
        with (cls.output/'ml64.log').open('wb') as log:
            subprocess.run([ML64,'/nologo','/c','/Fo'+str(cls.obj),cls.asm],stdout=log,stderr=subprocess.STDOUT,check=True)
        cls.raw=cls.obj.read_bytes();cls.dll=cls.output/'roots.dll'
        with (cls.output/'link.log').open('wb') as log:
            subprocess.run([ML64.with_name('link.exe'),'/nologo','/DLL','/NOENTRY','/NODEFAULTLIB','/MACHINE:X64','/OUT:'+str(cls.dll),
                cls.obj,*['/EXPORT:'+name for name in ('boom_provider_native_roots_snapshot','boom_fixture_root_a','boom_fixture_root_b','boom_fixture_metadata')]],
                stdout=log,stderr=subprocess.STDOUT,check=True)
        cls.image=c.CDLL(str(cls.dll));cls.snapshot=cls.image.boom_provider_native_roots_snapshot
        cls.snapshot.restype=U;cls.snapshot.argtypes=[P,U,P,U,P]
        cls.proof=N.verify_object(cls.obj,DECL,assembly=cls.asm)

    def setUp(self):
        self.a=(Q*4).in_dll(self.image,'boom_fixture_root_a');self.b=(Q*3).in_dll(self.image,'boom_fixture_root_b')
        for bank in (self.a,self.b):
            for i in range(len(bank)):bank[i]=0

    def mutation(self,raw):
        p=self.output/(self.id().split('.')[-1]+'.obj');p.write_bytes(raw);return p

    def reject(self,raw,message):
        with self.assertRaisesRegex(ValueError,message):N.verify_object(self.mutation(raw),DECL,assembly=self.asm)

    def test_actual_arrays_are_complete_writable_zero_QWORD_spans(self):
        self.assertEqual([(r['offset'],r['bytes']) for r in self.proof],[(0,32),(32,24)])
        self.assertTrue(all(r['physical_QWORD_span_verified'] and r['initial_zero'] for r in self.proof))

    def test_readonly_metadata_cannot_be_a_root(self):
        raw=bytearray(self.raw);_,_,section=symbol_at(raw,DECL[0]['symbol']);at=20+40*(section-1)+36
        struct.pack_into('<I',raw,at,struct.unpack_from('<I',raw,at)[0]&~0x80000000)
        self.reject(raw,'read-only')

    def test_executable_metadata_cannot_be_a_root(self):
        raw=bytearray(self.raw);_,_,section=symbol_at(raw,DECL[0]['symbol']);at=20+40*(section-1)+36
        struct.pack_into('<I',raw,at,struct.unpack_from('<I',raw,at)[0]|0x20000000)
        self.reject(raw,'executable')

    def test_an_unchanged_name_moved_into_the_next_bank_is_rejected(self):
        raw=bytearray(self.raw);at,value,_=symbol_at(raw,DECL[0]['symbol']);struct.pack_into('<I',raw,at+8,value+8)
        self.reject(raw,'intrudes')

    def test_private_symbol_intrusion_is_rejected(self):
        raw=bytearray(self.raw);at,_,_=symbol_at(raw,'boom_fixture_scalar');struct.pack_into('<I',raw,at+8,8);raw[at+16]=3
        self.reject(raw,'intrudes')

    def test_nonzero_initial_oop_is_rejected(self):
        raw=bytearray(self.raw);_,value,section=symbol_at(raw,DECL[0]['symbol'])
        position=struct.unpack_from('<I',raw,20+40*(section-1)+20)[0];raw[position+value]=1
        self.reject(raw,'not all zero')

    def test_partial_section_bounds_are_rejected(self):
        raw=bytearray(self.raw);at,value,section=symbol_at(raw,DECL[1]['symbol']);struct.pack_into('<I',raw,at+8,value+1024)
        self.reject(raw,'physical span')

    def test_native_pointer_relocation_is_rejected(self):
        # Move the symbol onto the read-only metadata's real ADDR64 relocation,
        # then grant WRITE: relocation rejection must precede any byte check.
        raw=bytearray(self.raw);root,_,_=symbol_at(raw,DECL[0]['symbol']);meta,value,section=symbol_at(raw,'boom_fixture_metadata')
        struct.pack_into('<Ih',raw,root+8,value,section)
        struct.pack_into('<I',raw,meta+8,32)
        header=20+40*(section-1);flags=struct.unpack_from('<I',raw,header+36)[0]
        struct.pack_into('<I',raw,header+36,flags|0x80000000)
        self.reject(raw,'relocation')

    def test_manifest_cannot_omit_source_roots(self):
        manifest=dict(exports=[r['symbol'] for r in DECL],object=N.artifact(self.obj),assembly=N.artifact(self.asm))
        with self.assertRaisesRegex(ValueError,'omitted'):N.provider_projection(manifest,dict(native_root_spans=DECL))

    def test_uninitialized_bss_is_physically_verified(self):
        [proof]=N.verify_object(self.obj,[dict(symbol='boom_fixture_bss',count=2,kind='test_oop_cells')],assembly=self.asm)
        self.assertEqual((proof['section'],proof['bytes'],proof['initial_zero']),('.bss',16,True))

    def test_array_source_length_must_match_the_physical_declaration(self):
        wrong=[dict(DECL[0],count=3)]
        with self.assertRaisesRegex(ValueError,'exact PUBLIC'):N.verify_object(self.obj,wrong,assembly=self.asm)

    def test_manifest_must_export_its_real_root_symbol(self):
        manifest=dict(exports=[],object=N.artifact(self.obj),assembly=N.artifact(self.asm),native_root_spans=DECL)
        with self.assertRaisesRegex(ValueError,'exported symbol'):N.provider_projection(manifest,dict(native_root_spans=DECL))

    def test_directory_cannot_trust_a_physical_verification_boolean(self):
        fake=[dict(self.proof[0],offset=8)]
        with self.assertRaisesRegex(ValueError,'physical proof'):N.directory_assembly(fake)

    def test_full_consumer_cannot_omit_normal_or_primordial_roots(self):
        with self.assertRaisesRegex(ValueError,'ordinary or primordial'):N.complete_consumer_assembly(self.proof,source_exports=[])

    def test_projection_selects_only_linked_selected_provider(self):
        packs=[]
        for i,decl in enumerate(DECL):
            manifest=dict(family='fixture-'+str(i),exports=[decl['symbol']],native_root_spans=[decl],object=N.artifact(self.obj),assembly=N.artifact(self.asm))
            path=self.output/('manifest-'+str(i)+'.json');path.write_text(json.dumps(manifest))
            ref=N.artifact(path);proof=path.with_name(path.stem+'-verification.json')
            proof.write_text(json.dumps(dict(verified=True,provider_manifest_sha256=ref['digest']['sha256'],scope='unit_fixture_only')))
            packs.append(dict(manifest=manifest,reference=ref,verification=N.artifact(proof)))
        result=N.selection(packs,[1],[str(self.obj)])
        self.assertEqual([r['symbol'] for r in result],[DECL[1]['symbol']])
        with self.assertRaisesRegex(ValueError,'exactly once'):N.selection(packs,[1],[])
        with self.assertRaisesRegex(ValueError,'exactly once'):N.selection(packs,[1],[str(self.obj)]*2)
        with self.assertRaisesRegex(ValueError,'index set'):N.selection(packs,[1,1],[str(self.obj)])

    def test_snapshot_retains_every_nonzero_oop_and_duplicate(self):
        self.a[:]=[123,0,456,123];self.b[:]=[0,789,0]
        before=bytes(self.a)+bytes(self.b);out=(Q*8)(*[0xab]*8);count=Q(0xcd)
        table=(Q*4).in_dll(self.image,'boom_fixture_metadata')
        self.assertEqual(self.snapshot(table,2,out,8,c.byref(count)),0)
        self.assertEqual(list(out[:count.value]),[123,456,123,789])
        self.assertEqual(list(out[4:]),[0xab]*4);self.assertEqual(bytes(self.a)+bytes(self.b),before)

    def test_snapshot_capacity_failure_is_transactional(self):
        self.a[:]=[1,2,3,4];out=(Q*2)(55,66);count=Q(77)
        table=(Q*4).in_dll(self.image,'boom_fixture_metadata')
        self.assertEqual(self.snapshot(table,2,out,2,c.byref(count)),122)
        self.assertEqual((list(out),count.value),([55,66],77))

    def test_snapshot_cannot_write_root_cells_or_its_directory(self):
        self.a[:]=[1,2,3,4];table=(Q*4).in_dll(self.image,'boom_fixture_metadata');before=bytes(self.a);count=Q(77)
        self.assertEqual(self.snapshot(table,2,self.a,4,c.byref(count)),87);self.assertEqual(bytes(self.a),before)
        out=(Q*8)(*[33]*8)
        self.assertEqual(self.snapshot(table,2,out,8,self.a),87);self.assertEqual(bytes(self.a),before)
        self.assertEqual(self.snapshot(table,2,out,8,table),87);self.assertEqual(list(out),[33]*8)

    def test_empty_snapshot_publishes_zero(self):
        count=Q(77);self.assertEqual(self.snapshot(None,0,None,0,c.byref(count)),0);self.assertEqual(count.value,0)

    def test_invalid_limits_and_unaligned_span_are_rejected(self):
        count=Q(77);out=(Q*8)(*[33]*8);table=(Q*2)(c.addressof(self.a)+1,1)
        self.assertEqual(self.snapshot(table,1,out,8,c.byref(count)),87)
        self.assertEqual(self.snapshot(table,4097,out,8,c.byref(count)),87)
        self.assertEqual(self.snapshot(table,1,out,1048577,c.byref(count)),87)
        self.assertEqual((list(out),count.value),([33]*8,77))

    def test_address_overflow_is_rejected_before_a_root_read(self):
        count=Q(77);out=(Q*8)(*[33]*8);table=(Q*2)(0xfffffffffffffff8,2)
        self.assertEqual(self.snapshot(table,1,out,8,c.byref(count)),87)
        self.assertEqual((list(out),count.value),([33]*8,77))


if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(NativeProviderRoots)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if hasattr(NativeProviderRoots,'output'):
        proof=dict(verified=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
            scope='real_COFF_physical_native_roots_and_quiescent_ASM_snapshot_unit_tests',helper=N.artifact(Path(N.__file__)),
            test=N.artifact(Path(__file__)),kernel=N.artifact(ROOT/'native/kernels/provider_native_root_snapshot.asm.inc'),
            fixture_assembly=N.artifact(NativeProviderRoots.asm),fixture_object=N.artifact(NativeProviderRoots.obj),
            physical_spans=NativeProviderRoots.proof,automatic_GC=False)
        path=NativeProviderRoots.output/'result.json';path.write_text(json.dumps(proof,indent=2)+'\n');print(path)
    raise SystemExit(0 if result.wasSuccessful() else 1)
