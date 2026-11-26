"""Seed extensions keep prior execution evidence distinct from new boot roots."""
import importlib.util
from pathlib import Path
import unittest
SPEC=importlib.util.spec_from_file_location('diagnostic_seed_root_extension',Path(__file__).resolve().parents[1]/'scripts/seed-diagnostic-profile.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)
class RootExtensionTests(unittest.TestCase):
    def test_unchanged_roots_preserve_old_receipt_shape(self):
        self.assertIsNone(M.root_extension(['bootstrap:java/lang/System'],['bootstrap:java/lang/System'],False))
    def test_added_roots_require_explicit_scope_and_actual_execution(self):
        old=['bootstrap:java/lang/System'];new=['bootstrap:java/lang/String',*old,'bootstrap:java/lang/reflect/Method']
        with self.assertRaises(ValueError):M.root_extension(old,new,False)
        r=M.root_extension(old,new,True)
        self.assertEqual(r['additional_class_roots'],[new[0],new[2]])
        self.assertFalse(r['full_VM_bootstrap'])
    def test_removing_reordering_or_duplicate_roots_is_rejected(self):
        old=['one','two']
        for new in (['one'],['two','one'],['one','two','two']):
            with self.subTest(new=new),self.assertRaises(ValueError):M.root_extension(old,new,True)
if __name__=='__main__':unittest.main()
