"""Reject source, declaration and post-initializer forgery in Unsafe bindings."""
import copy
import importlib.util
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location('unsafe_verifier',Path(__file__).resolve().parents[1]/'scripts/verify-batch-unsafe.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)


def inputs():
    cls=dict(id=0,name=M.OWNER,access=0x31,origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='unsafe'),method_ids=list(range(4)))
    const=dict(id=1,name=M.CONSTANTS,access=0x30,origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='constants'),
               method_ids=[4],fields=[dict(name=n,descriptor=d,access=0x18) for n,d in M.FIELDS])
    inv={i:(0,n,d,'unsafe',None,0,0,0,f) for i,(n,d,f,_) in enumerate(M.SPECS)}
    inv[4]=(1,'<clinit>','()V','constants','code',21,0,1,8)
    state=dict(source_sha256='constants',diagnostic=None,vm_post_initializer='unsafe_constants',
               initializer=dict(method=4,code_sha256='code',assembly_emitted=True),
               fields=[dict(constant=None,initial_bits=0,reference=False) for _ in M.FIELDS])
    types=[dict(id=i,kind=k,name=n) for i,(k,n) in enumerate([(1,'java/lang/Object'),(0,'I'),(3,'[I'),(3,'[[I'),(3,'[B'),(3,'[S')])]
    return [cls,const],inv,types,{1:state}


class UnsafeVerifierTests(unittest.TestCase):
    def test_normal_array_shapes_and_only_source_natives(self):
        cls,const,methods,scales,init=M.source_contract(*inputs())
        self.assertEqual(scales,[0,0,4,8,1,2])
        self.assertEqual([m['operation'] for m in methods],[0,1,2,3])

    def test_wrong_native_class_source_code_or_access_rejected(self):
        for column,value in [(0,1),(3,'other'),(4,'Java Code'),(8,0x109)]:
            a=inputs();r=list(a[1][1]);r[column]=value;a[1][1]=tuple(r)
            with self.subTest(column=column),self.assertRaises(ValueError):M.source_contract(*a)

    def test_generated_or_application_vm_identity_rejected(self):
        for index in (0,1):
            for key,val in [('loader','application'),('source_id','application'),('generated',{'host':'x'})]:
                a=inputs();a[0][index]['origin'][key]=val
                with self.subTest(index=index,key=key),self.assertRaises(ValueError):M.source_contract(*a)

    def test_zero_constant_or_source_initializer_cannot_be_replaced(self):
        for change in ('code','missing','preinitialized','hook'):
            a=inputs();s=a[3][1]
            if change=='code':s['initializer']['code_sha256']='other'
            elif change=='missing':s['initializer']['assembly_emitted']=False
            elif change=='preinitialized':s['fields'][0]['initial_bits']=8
            else:s['vm_post_initializer']='other'
            with self.subTest(change=change),self.assertRaises(ValueError):M.source_contract(*a)

    def test_reordered_or_foreign_constant_fields_rejected(self):
        for change in ('order','type','static'):
            a=inputs();fields=a[0][1]['fields']
            if change=='order':fields.reverse()
            elif change=='type':fields[0]['descriptor']='J'
            else:fields[0]['access']=0x10
            with self.subTest(change=change),self.assertRaises(ValueError):M.source_contract(*a)

    def test_type_identity_cannot_be_reindexed(self):
        a=inputs();a[2][2]['id']=7
        with self.assertRaises(ValueError):M.source_contract(*a)

    def test_missing_optional_types_keep_source_ids_and_zero_entries(self):
        a=inputs();a[2].pop(3)
        result=M.source_contract(*a,capacity=6)
        self.assertEqual(result[3],[0,0,4,0,1,2])

    def test_duplicate_types_do_not_replace_missing_ones(self):
        a=inputs();a[2][3]=copy.deepcopy(a[2][2])
        with self.assertRaises(ValueError):M.source_contract(*a)


if __name__=='__main__':unittest.main()
