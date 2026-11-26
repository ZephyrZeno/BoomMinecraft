import importlib.util
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location('unsafe_memory_verifier',Path(__file__).resolve().parents[1]/'scripts/verify-batch-unsafe-memory.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)

def inputs():
    c=dict(id=3,name=M.OWNER,access=0x31,origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='unsafe'),method_ids=[])
    inv={}
    for i,(name,desc,flags,op) in enumerate(M.specs(),10):
        c['method_ids'].append(i);inv[i]=(3,name,desc,'unsafe',None,0,0,0,flags)
    # Same-name absolute access stays a Java method, never a fabricated native.
    c['method_ids'].append(99);inv[99]=(3,'getInt','(J)I','unsafe','original-Java',0,0,0,1)
    return [c],inv

class UnsafeMemoryVerifierTests(unittest.TestCase):
    def test_all_typed_heap_operations_are_distinct_and_source_bound(self):
        c,m=M.source_contract(*inputs());self.assertEqual(len(m),42)
        self.assertEqual(len({x['operation'] for x in m}),42)
        self.assertNotIn(99,{x['method'] for x in m})
        self.assertEqual(sum(x['access']==0x111 for x in m),6)
        self.assertTrue(all(x['descriptor'].startswith('(Ljava/lang/Object;J') for x in m))

    def test_same_name_absolute_overload_cannot_fill_a_missing_native(self):
        classes,inv=inputs();id_=next(i for i,m in inv.items() if m[1:3]==('getInt','(Ljava/lang/Object;J)I'))
        classes[0]['method_ids'].remove(id_)
        with self.assertRaises(ValueError):M.source_contract(classes,inv)

    def test_native_flags_code_and_class_identity_are_exact(self):
        for column,value in ((0,4),(3,'changed'),(4,'Code'),(8,0x111)):
            c,inv=inputs();row=list(inv[10]);row[column]=value;inv[10]=tuple(row)
            with self.subTest(column=column),self.assertRaises(ValueError):M.source_contract(c,inv)

    def test_other_loader_or_generated_source_is_not_accepted(self):
        for key,value in (('loader','application'),('source_id','application'),('generated',{'host':'x'})):
            c,inv=inputs();c[0]['origin'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):M.source_contract(c,inv)

    def test_atomic_signatures_keep_expected_desired_and_return_witness(self):
        specs={name:(desc,flags,op) for name,desc,flags,op in M.specs()}
        self.assertEqual(specs['compareAndSetInt'],('(Ljava/lang/Object;JII)Z',0x111,69))
        self.assertEqual(specs['compareAndExchangeLong'],('(Ljava/lang/Object;JJJ)J',0x111,86))
        self.assertEqual(specs['compareAndExchangeReference'][2],89)

    def test_source_initialization_and_shared_pool_stay_in_adapter(self):
        _,methods=M.source_contract(*inputs());text=M.body(methods[0])
        self.assertIn('call boom_class_ensure32',text);self.assertIn('lea r8,boom_java_unsafe_field_pool',text)
        self.assertIn('jmp boom_java_unsafe_memory',text);self.assertNotIn('boom_java_unsafe_field_address',text)

if __name__=='__main__':unittest.main()
