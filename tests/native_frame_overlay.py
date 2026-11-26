"""Preserve base frame identities while admitting original native declarations."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('native_frame_overlay_tests',Path(__file__).resolve().parents[1]/'scripts/native-frame-overlay.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


class NativeFrameOverlayTests(unittest.TestCase):
    def test_native_rows_merge_by_original_id_and_preserve_existing_rows(self):
        base=[(2,0,1,8),(20,40,3,0),(50,0,4,11)]
        rows,added=M.merge(base,[(20,40,3,0),(10,32,2,0)])
        self.assertEqual(rows,[base[0],(10,32,2,0),base[1],base[2]])
        self.assertEqual(added,[10]);self.assertEqual([r for r in rows if r[0] in {2,20,50}],base)

    def test_collisions_duplicates_non_native_code_and_capacity_are_rejected(self):
        base=[(2,0,1,8)]
        for native in [[(2,32,1,0)],[(10,32,2,0),(10,32,2,0)],[(10,0,2,0)],[(10,32,2,1)],[(10,0x120,2,0)]]:
            with self.subTest(native=native),self.assertRaises(ValueError):M.merge(base,native)
        with self.assertRaisesRegex(ValueError,'capacity'):M.merge(base,[(10,32,2,0)],limit=1)
        with self.assertRaisesRegex(ValueError,'unordered'):M.merge([(2,0,1,8),(1,0,1,8)],[])

    def test_unavailable_source_has_no_fabricated_declaring_type(self):
        rows=[(2,0,1,8),(10,160,2,0)];text=M.assembly(rows);exports,imports=M.symbols(rows)
        self.assertIn('boom_trace_method10 DWORD 10,160\n QWORD 0\n DWORD 0,2',text)
        self.assertNotIn('boom_t2',imports);self.assertIn('boom_trace_method10',exports)
        self.assertIn('boom_trace_pool DWORD 05452504Ch,3',text)

    def test_raw_native_contract_rejects_java_bodies_and_changed_plan_identity(self):
        source=dict(id=3,origin=dict(sha256='a'*64))
        plan=dict(class_id=3,class_sha256='a'*64,code_sha256=None,access=0x109,symbol=dict(name='call',descriptor='()V'))
        raw=dict(name='call',descriptor='()V',access=0x109,code=None)
        M.native_contract(source,plan,raw)
        for key,value in [('code',(b'\xb1',0,0)),('access',0x509),('name','other')]:
            bad=copy.deepcopy(raw);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):M.native_contract(source,plan,bad)
        bad=copy.deepcopy(plan);bad['class_sha256']='b'*64
        with self.assertRaises(ValueError):M.native_contract(source,bad,raw)


if __name__=='__main__':unittest.main()
