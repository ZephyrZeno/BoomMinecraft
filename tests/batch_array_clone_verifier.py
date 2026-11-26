import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('array_clone_verifier',ROOT/'scripts/verify-batch-array-clone.py')
V=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(V)

class CloneSourceTests(unittest.TestCase):
    def member(self,owner):return dict(owner=owner,name='clone',descriptor='()Ljava/lang/Object;',interface=False)
    def test_optional_generated_origin_omission_matches_none_but_rejects_generated_sources(self):
        source=dict(name='java/lang/Object',access=0x21,origin=dict(loader='bootstrap',source_id='jdk:java.base'))
        self.assertTrue(V.original_object(source))
        self.assertTrue(V.original_object(dict(source,origin=dict(source['origin'],generated=None))))
        self.assertFalse(V.original_object(dict(source,origin=dict(source['origin'],generated={}))))
        self.assertFalse(V.original_object(dict(source,origin=dict(source['origin'],loader='vanilla-application'))))
    def test_component_defining_loader_is_preserved_for_nested_arrays(self):
        classes=[dict(origin=dict(loader='vanilla-application')),dict(origin=dict(loader='platform'))]
        lookup=lambda loader,name:1 if name=='p/T' else None
        arrays={('platform','[[Lp/T;'):7,('vanilla-application','[[Lp/T;'):8}
        self.assertEqual(V.source_array(self.member('[[Lp/T;'),0,classes,lookup,arrays),7)
        with self.assertRaisesRegex(ValueError,'loader/type'):
            V.source_array(self.member('[[Lp/T;'),0,classes,lookup,{('vanilla-application','[[Lp/T;'):8})
    def test_primitive_array_uses_bootstrap_even_for_application_caller(self):
        self.assertEqual(V.source_array(self.member('[[D'),0,[dict(origin=dict(loader='vanilla-application'))],
                                       lambda *_:None,{('bootstrap','[[D'):42}),42)
    def test_no_void_nonarray_or_interface_clone_contract(self):
        classes=[dict(origin=dict(loader='bootstrap'))]
        for member in [self.member('[V'),self.member('java/lang/Object'),dict(self.member('[I'),interface=True),dict(self.member('[I'),name='copy')]:
            with self.assertRaises(ValueError):V.source_array(member,0,classes,lambda *_:None,{('bootstrap','[I'):7})

if __name__=='__main__':unittest.main()
