"""Selected constructor data must never call an unready Java entry as a ctor."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('constructor_invocation_selection_tests',Path(__file__).resolve().parents[1]/'scripts/constructor-invocation-source.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


def metadata():
    return dict(records=[dict(owner=1,slot=0,method=10,modifiers=1,available=True,noninstantiable=False,parameters=[dict(kind=4,type_id=5)]),
        dict(owner=2,slot=0,method=20,modifiers=1,available=True,noninstantiable=False,parameters=[]),
        dict(owner=3,slot=0,method=30,modifiers=1,available=False,noninstantiable=False,parameters=[])])


class ConstructorInvocationSelectionTests(unittest.TestCase):
    def test_ready_site_requires_both_class_and_original_body(self):
        text,methods,classes,ready=M.selected_sites(metadata(),{1},{10})
        self.assertEqual(ready,[0]);self.assertEqual(methods,set());self.assertEqual(classes,{2})
        self.assertIn('QWORD OFFSET provider_cinvoke_site0,0',text)
        self.assertIn('QWORD 0,OFFSET boom_batch_initialize_2',text)
        self.assertIn('DWORD 4,5\n QWORD 0',text)
        self.assertIn('OFFSET boom_layout1,OFFSET boom_class1,OFFSET boom_m10',text)

    def test_selected_class_without_body_uses_method_diagnostic(self):
        text,methods,classes,ready=M.selected_sites(metadata(),{1,2},{20})
        self.assertEqual(methods,{10});self.assertEqual(classes,set());self.assertEqual(ready,[1])
        self.assertIn('QWORD 0,OFFSET boom_m10',text)
        self.assertNotIn('provider_cinvoke_site0 DWORD',text)

    def test_unavailable_metadata_is_not_fabricated_or_admitted(self):
        text,methods,classes,ready=M.selected_sites(metadata(),{1,2,3},{10,20,30})
        self.assertEqual(ready,[0,1]);self.assertFalse(methods or classes)
        self.assertNotIn('OFFSET boom_m30',text);self.assertNotIn('provider_cinvoke_site2 DWORD',text)

    def test_reference_parameters_retain_original_type_descriptor(self):
        m=metadata();m['records'][0]['parameters']=[dict(kind=8,type_id=17)]
        text,_,_,_=M.selected_sites(m,{1},{10})
        self.assertIn('DWORD 8,17\n QWORD OFFSET boom_t17',text)

    def test_combined_kernel_keeps_helpers_local_and_preserves_runtime_imports(self):
        text,imports=M.kernel_text(Path(__file__).resolve().parents[1])
        self.assertNotIn('EXTERN ',text)
        self.assertTrue(M.HELPERS.isdisjoint(imports));self.assertIn('boom_runtime_instanceof',imports)
        self.assertIn('PUBLIC boom_provider_constructor_invoke_service',text)


if __name__=='__main__':unittest.main()
