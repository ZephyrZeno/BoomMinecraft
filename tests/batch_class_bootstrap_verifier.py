"""Reject forged bootstrap declarations, primitive identities and AOT bindings."""
import copy
import importlib.util
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location('class_bootstrap_verifier',Path(__file__).resolve().parents[1]/'scripts/verify-batch-class-bootstrap.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)


def inputs():
    cls=dict(id=1,name='java/lang/Class',access=0x31,origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='original'),method_ids=[])
    inventory={};core=[]
    for i,(name,desc,access,op) in enumerate(M.SPECS,10):
        cls['method_ids'].append(i);inventory[i]=(1,name,desc,'original',None,0,0,0,access)
    for i,(name,desc,access,op) in enumerate(M.CORE,20):
        cls['method_ids'].append(i);inventory[i]=(1,name,desc,'original',None,0,0,0,access)
        core.append(dict(method=i,class_id=1,operation=op,access=access))
    types=[dict(id=100+i,kind=0,name=d,defining_loader='bootstrap') for i,(d,n) in enumerate(M.PRIMITIVES)]
    return [cls],inventory,types,core


class ClassBootstrapVerifierTests(unittest.TestCase):
    def test_real_native_and_primitive_contract(self):
        cls,methods,types,registration=M.source_contract(*inputs())
        self.assertEqual([m['operation'] for m in methods],[0,10,11])
        self.assertEqual([t['name'] for t in types],[n for d,n in M.PRIMITIVES])
        self.assertEqual([r['operation'] for r in registration],list(range(1,9))+[10,11])

    def test_native_flags_source_identity_and_code_are_not_interchangeable(self):
        for column,value in [(0,2),(3,'modified'),(4,'unexpected Code'),(8,0x109)]:
            args=inputs();row=list(args[1][10]);row[column]=value;args[1][10]=tuple(row)
            with self.subTest(column=column),self.assertRaises(ValueError):M.source_contract(*args)

    def test_vm_core_identity_cannot_be_spoofed(self):
        for key,value in [('source_id','application'),('generated',dict(host='x')),('loader','application')]:
            args=inputs();args[0][0]['origin'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):M.source_contract(*args)

    def test_primitive_rows_require_unique_bootstrap_identity(self):
        for change in ('duplicate','reference','loader'):
            args=inputs()
            if change=='duplicate':args[2].append(copy.deepcopy(args[2][0]))
            elif change=='reference':args[2][0]['kind']=1
            else:args[2][0]['defining_loader']='application'
            with self.subTest(change=change),self.assertRaises(ValueError):M.source_contract(*args)

    def test_prelinked_table_does_not_replace_missing_or_wrong_natives(self):
        for key,value in [('operation',0),('access',0x109),('class_id',2)]:
            args=inputs();args[3][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):M.source_contract(*args)

    def test_emitted_entry_keeps_pending_error_and_source_initializer(self):
        b=M.body(10,1,0)
        self.assertLess(b.index('cmp DWORD PTR [rcx],0'),b.index('call boom_class_ensure32'))
        self.assertLess(b.index('call boom_class_ensure32'),b.index('call boom_m10_native'))
        self.assertNotIn('mov DWORD PTR [boom_class1+8],2',b)
        self.assertIn('jmp boom_java_class_bootstrap',b)


if __name__=='__main__':unittest.main()
