"""Independent initialization ordering and ConstantValue rejection properties."""
import importlib.util
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location('class_state_verifier',Path(__file__).resolve().parents[1]/'scripts/verify-batch-class-state.py')
V=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(V)

class ClassStateTests(unittest.TestCase):
    def test_raw_constant_bits_and_narrow_signed_values(self):
        self.assertEqual(V.constant_bits('B',{'Int':255},2),(0xffffffff,None))
        self.assertEqual(V.constant_bits('S',{'Int':32768},2),(0xffff8000,None))
        self.assertEqual(V.constant_bits('C',{'Int':-1},2),(65535,None))
        self.assertEqual(V.constant_bits('D',{'DoubleBits':0x8000000000000000},2),(0x8000000000000000,None))
        with self.assertRaises(ValueError):V.constant_bits('I',{'Long':1},2)
        with self.assertRaises(ValueError):V.constant_bits('Ljava/lang/Object;',{'StringUtf16':[]},2)

    def test_superclass_then_recursive_interfaces_and_shared_parent_once(self):
        def c(name,flags,parent,interfaces=()):return dict(name=name,access=flags,superclass=parent,interfaces=list(interfaces),origin=dict(loader='bootstrap'))
        classes=[c('Object',1,''),c('Base',1,'Object'),c('A',0x601,'Object'),c('B',0x601,'Object',['A']),
                 c('C',0x601,'Object',['A']),c('Leaf',1,'Base',['B','C'])]
        names={c['name']:i for i,c in enumerate(classes)};parents={0:None,1:0,2:0,3:0,4:0,5:1}
        inputs={i:dict(concrete_instance_method=i in (2,3,4)) for i in range(len(classes))}
        self.assertEqual(V.dependencies(classes,inputs,lambda loader,name:names.get(name),parents,5),[1,2,3,4])
        self.assertEqual(V.dependencies(classes,inputs,lambda loader,name:names.get(name),parents,3),[])

    def test_constant_assignment_precedes_dependencies_and_unwrapped_clinit(self):
        state=dict(class_id=5,fields=[dict(index=0,constant=2,string_constant=None,initial_bits=17),
                                    dict(index=1,constant=3,string_constant=3,initial_bits=0)],dependencies=[1,2],initializer=dict(method=40))
        body=V.initialization_body(state)
        self.assertLess(body.index('mov QWORD PTR [boom_s5_0],rax'),body.index('lea rcx,boom_class1'))
        self.assertLess(body.index('call boom_batch_literal_load_5_3'),body.index('lea rcx,boom_class1'))
        self.assertLess(body.index('lea rcx,boom_class2'),body.index('call boom_m40_body'))
        self.assertNotIn('call boom_m40\n',body)

if __name__=='__main__':unittest.main()
