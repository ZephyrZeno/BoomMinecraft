"""Extra source requests retain the exact primordial prefix and make no admissions."""
import importlib.util
from pathlib import Path
import unittest


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('vm_explicit_source_roots',ROOT/'scripts/prepare-normal-vm-thread-bootstrap.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


class AdditionalSourceRoots(unittest.TestCase):
    def test_empty_request_retains_the_original_prefix(self):
        roots=[('bootstrap',name) for name in ('java/lang/String','java/lang/System','java/lang/Class','java/lang/reflect/Method')]
        actual=M.append_source_roots(roots,[],2)
        self.assertEqual(actual,roots);self.assertIsNot(actual,roots)

    def test_required_class_repeats_do_not_reorder_VM_prerequisites(self):
        roots=[('bootstrap','java/lang/Class'),('bootstrap','java/lang/String')]
        required=[roots[1],('bootstrap','jdk/internal/reflect/ConstantPool'),roots[0],('bootstrap','jdk/internal/reflect/ConstantPool')]
        self.assertEqual(M.append_source_roots(roots,required,2),roots+[required[1]])
        self.assertEqual(roots,[('bootstrap','java/lang/Class'),('bootstrap','java/lang/String')])

    def test_loader_identity_and_complete_method_descriptor_are_retained(self):
        roots=[('bootstrap','a/C','f','()V')]
        extra=[('vanilla-application','a/C','f','()V'),('bootstrap','a/C','f','(Ljava/lang/Class;I)[Ljava/lang/String;')]
        self.assertEqual(M.append_source_roots(roots,extra,4),roots+extra)

    def test_bad_root_shapes_are_rejected_before_selection(self):
        for width,rows in ((2,['bootstrap:C']),(2,[('bootstrap',)]),(2,[('bootstrap','')]),
                           (2,[(None,'C')]),(4,[('bootstrap','C','f')]),(4,[('bootstrap','C','f',None)])):
            with self.subTest(rows=rows),self.assertRaisesRegex(ValueError,'Invalid additional source root'):
                M.append_source_roots([],rows,width)


if __name__=='__main__':unittest.main()
