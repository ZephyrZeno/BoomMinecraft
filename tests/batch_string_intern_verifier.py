import copy
import importlib.util
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location('intern_source_verifier',Path(__file__).resolve().parents[1]/'scripts/verify-batch-string-intern.py')
V=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(V)


class InternSourceTests(unittest.TestCase):
    def model(self):
        owner=dict(id=0,name='java/lang/String',access=0x31,method_ids=[0],origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='source'))
        inventory=[(0,'intern','()Ljava/lang/String;','source',None,0,0,0,0x101)]
        shape=dict(class_id=0,source_sha256='source',value_offset=0,coder_offset=12,hash_offset=8,hash_is_zero_offset=13)
        return owner,inventory,shape

    def test_original_native_declaration_is_required(self):
        c,m,s=self.model();self.assertEqual(V.source_method([c],m,s)['method'],0)
        for field,value in (('loader','application'),('source_id','replacement'),('sha256','changed')):
            changed=copy.deepcopy(c);changed['origin'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):V.source_method([changed],m,s)

    def test_static_or_java_body_cannot_masquerade_as_instance_native(self):
        c,m,s=self.model()
        for index,value in ((4,'Java_Code'),(8,0x109),(2,'()Ljava/lang/Object;')):
            changed=[list(m[0])];changed[0][index]=value;changed=[tuple(changed[0])]
            with self.subTest(index=index),self.assertRaises(ValueError):V.source_method([c],changed,s)

    def test_canonical_pools_share_the_normal_source_heap_and_layout(self):
        _,_,shape=self.model();body=V.pool(shape)
        self.assertIn('OFFSET boom_heap_ptr,OFFSET boom_layout0',body)
        self.assertIn('DWORD 0,12,8,13',body)
        self.assertIn('OFFSET boom_java_string_literal_pool,OFFSET boom_java_class_name_pool',body)
        self.assertIn('boom_java_string_intern_root_count QWORD 1',body)

    def test_instance_native_does_not_initialize_String(self):
        body=V.body(42);self.assertIn('jmp boom_java_string_intern',body);self.assertNotIn('class_ensure',body)


if __name__=='__main__':unittest.main()
