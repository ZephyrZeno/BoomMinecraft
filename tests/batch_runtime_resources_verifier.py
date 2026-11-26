import importlib.util
from pathlib import Path
import unittest

S=importlib.util.spec_from_file_location('runtime_resources_verifier',Path(__file__).resolve().parents[1]/'scripts/verify-batch-runtime-resources.py');M=importlib.util.module_from_spec(S);S.loader.exec_module(M)


def inputs():
    c=dict(id=4,name='java/lang/Runtime',access=0x21,origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='source'),method_ids=[9,10,11,12,13,14])
    inv={9:(4,'<init>','()V','source','java-code',0,0,0,2),14:(4,'gc','()V','source',None,0,0,0,0x101)}
    inv.update({10+i:(4,n,d,'source',None,0,0,0,f) for i,(n,d,f,_) in enumerate(M.SPECS)})
    return [c],inv


class RuntimeResourceVerifierTests(unittest.TestCase):
    def test_four_original_natives_do_not_supply_gc(self):
        c,methods=M.source_contract(*inputs());self.assertEqual([m['operation'] for m in methods],[0,1,2,3]);self.assertNotIn(14,[m['method'] for m in methods])

    def test_native_source_flags_code_and_owner_are_checked(self):
        for col,v in [(0,5),(3,'other'),(4,'Code'),(8,0x109)]:
            a=inputs();r=list(a[1][10]);r[col]=v;a[1][10]=tuple(r)
            with self.subTest(col=col),self.assertRaises(ValueError):M.source_contract(*a)

    def test_private_original_constructor_required(self):
        for col,v in [(0,5),(2,'(I)V'),(3,'other'),(4,None),(8,1)]:
            a=inputs();r=list(a[1][9]);r[col]=v;a[1][9]=tuple(r)
            with self.subTest(col=col),self.assertRaises(ValueError):M.source_contract(*a)

    def test_modified_vm_identity_rejected(self):
        for key,v in [('loader','application'),('source_id','application'),('generated',{'host':'x'})]:
            a=inputs();a[0][0]['origin'][key]=v
            with self.subTest(key=key),self.assertRaises(ValueError):M.source_contract(*a)

    def test_missing_or_ambiguous_native_rejected(self):
        for change in ('missing','duplicate'):
            a=inputs()
            if change=='missing':a[0][0]['method_ids'].remove(10)
            else:a[0][0]['method_ids'].append(10)
            with self.subTest(change=change),self.assertRaises(ValueError):M.source_contract(*a)

    def test_pool_uses_real_heap_and_type_metadata(self):
        data=M.data(4);self.assertIn('OFFSET boom_heap_ptr,OFFSET boom_runtime_type_map,OFFSET boom_t4',data)
        self.assertNotIn('boom_mirror_pool',data)


if __name__=='__main__':unittest.main()
