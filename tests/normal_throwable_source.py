"""Normal backtrace fields must follow each subclass's actual physical layout."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('normal_throwable_source_tests',ROOT/'scripts/normal-throwable-source.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


def fixture():
    names=['java/lang/Object','java/lang/Throwable','example/Child']
    declarations=[dict(name=n,descriptor=d,access=a) for n,d,a in M.FIELDS]
    classes=[dict(id=i,name=name,access=1,superclass='' if i==0 else names[i-1],fields=copy.deepcopy(declarations) if i==1 else [],
        origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256=str(i))) for i,name in enumerate(names)]
    types=[dict(id=i,name=name,kind=1,parent_component=None if i==0 else i-1,ancestors=list(range(i)),defining_loader='bootstrap',source_sha256=str(i)) for i,name in enumerate(names)]
    runtime=[];layouts=[]
    for i,refs,depth in [(1,2,16),(2,3,24)]:
        fields=[]
        for index,(name,desc,access) in enumerate(M.FIELDS):
            fields.append(dict(member=dict(owner=1,index=index,name=name,descriptor=desc,access=access),
                offset=depth if name=='depth' else (0 if name=='backtrace' else 8),reference=desc!='I',storage_bytes=4 if desc=='I' else 8))
        runtime.append(dict(type_id=i,kind=0,tag_symbol='boom_layout'+str(i),payload_bytes=depth+4,reference_prefix=refs))
        layouts.append(dict(class_id=i,source_sha256=str(i),diagnostic=None,candidate=dict(payload_bytes=depth+4,reference_prefix=refs,fields=fields)))
    return classes,types,runtime,layouts


class NormalThrowableSourceTests(unittest.TestCase):
    def native_contract(self,access=0x102,code=None,generated=None):
        source=dict(id=1,name='java/lang/Throwable',method_ids=[42],origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='original',generated=generated))
        method=dict(name='fillInStackTrace',descriptor='(I)Ljava/lang/Throwable;',access=access,code=code)
        with mock.patch.object(M.S,'original_class',return_value=b'original class'),mock.patch.object(M.R,'original_methods',return_value=(source['name'],[method])):
            return M.contracts({},[source])

    def test_native_binds_the_original_private_instance_declaration(self):
        native=self.native_contract()[0]
        self.assertEqual((native['method'],native['class_id'],native['access'],native['operation']),(42,1,0x102,0))

    def test_rejects_static_or_public_native_declaration(self):
        for access in (0x10a,0x101):
            with self.subTest(access=access),self.assertRaisesRegex(ValueError,'native declaration'):self.native_contract(access=access)

    def test_rejects_Java_body_present_on_native_declaration(self):
        with self.assertRaisesRegex(ValueError,'native declaration'):self.native_contract(code=b'\xb0')

    def test_rejects_generated_Throwable_source(self):
        with self.assertRaisesRegex(ValueError,'original java.base'):self.native_contract(generated={'kind':'fixture'})

    def test_subclass_reference_prefix_moves_inherited_scalar_depth(self):
        args=fixture();root,rows=M.receiver_rows(*args)
        self.assertEqual(root,1);self.assertEqual([(r['class_id'],r['depth']) for r in rows],[(1,16),(2,24)])

    def test_rejects_fabricated_throwable_ancestry(self):
        c,t,r,l=fixture();c[2]['superclass']='java/lang/Object';t[2]['parent_component']=0
        with self.assertRaisesRegex(ValueError,'ancestry table'):M.receiver_rows(c,t,r,l)

    def test_rejects_omitted_real_throwable_ancestor(self):
        c,t,r,l=fixture();t[2]['ancestors']=[0]
        with self.assertRaisesRegex(ValueError,'ancestry table'):M.receiver_rows(c,t,r,l)

    def test_rejects_depth_in_the_reference_prefix(self):
        c,t,r,l=fixture();l[1]['candidate']['fields'][1]['offset']=16
        with self.assertRaisesRegex(ValueError,'bounds'):M.receiver_rows(c,t,r,l)


if __name__=='__main__':unittest.main()
