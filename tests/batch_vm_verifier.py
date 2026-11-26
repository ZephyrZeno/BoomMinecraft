import importlib.util
from pathlib import Path
import unittest

S=importlib.util.spec_from_file_location('vm_verifier',Path(__file__).resolve().parents[1]/'scripts/verify-batch-vm.py');M=importlib.util.module_from_spec(S);S.loader.exec_module(M)


def inputs():
    c=dict(id=4,name='jdk/internal/misc/VM',access=0x21,origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='source'),method_ids=[10,11])
    inv={10+i:(4,n,d,'source',None,0,0,0,f) for i,(n,d,f,_) in enumerate(M.SPECS)}
    return [c],inv


class VmVerifierTests(unittest.TestCase):
    def test_original_static_natives_only(self):
        c,methods=M.source_contract(*inputs());self.assertEqual([m['operation'] for m in methods],[0,1])

    def test_changed_native_code_flags_or_owner_rejected(self):
        for col,v in [(0,5),(3,'other'),(4,'Code'),(8,0x101)]:
            a=inputs();r=list(a[1][10]);r[col]=v;a[1][10]=tuple(r)
            with self.subTest(col=col),self.assertRaises(ValueError):M.source_contract(*a)

    def test_application_or_generated_vm_rejected(self):
        for key,v in [('loader','application'),('source_id','application'),('generated',{'host':'x'})]:
            a=inputs();a[0][0]['origin'][key]=v
            with self.subTest(key=key),self.assertRaises(ValueError):M.source_contract(*a)

    def test_missing_or_duplicate_vm_rejected(self):
        for classes in ([],inputs()[0]*2):
            with self.assertRaises(ValueError):M.source_contract(classes,inputs()[1])

    def test_import_thunk_is_not_a_preinitialized_runtime_target(self):
        self.assertIn('DWORD 0564D5247h,2,0,1\n QWORD 0,0',M.DATA)
        self.assertNotIn('OFFSET boom_vm_nano_adjustment',M.DATA)
        self.assertLess(M.body(10,4,0).index('cmp DWORD PTR [rcx],0'),M.body(10,4,0).index('call boom_class_ensure32'))


if __name__=='__main__':unittest.main()
