import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('batch_system_verifier',ROOT/'scripts/verify-batch-system.py')
V=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(V)

class SystemNativeSourceTests(unittest.TestCase):
    def source(self):
        c=dict(id=0,name='java/lang/System',access=0x31,superclass='java/lang/Object',method_ids=list(range(len(V.SPECS))),
               origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='sha'))
        methods=[(0,name,desc,'sha',None,0,0,0,access) for name,desc,access,_ in V.SPECS]
        return c,methods
    def test_registered_methods_and_private_registration_keep_source_identity(self):
        c,methods=self.source();source,rows=V.source_methods([c],methods)
        self.assertEqual([r['operation'] for r in rows],[None,0,1,2,3,4,5])
        self.assertEqual(rows[0]['access'],0x10a)
        for changed in (dict(c,access=0x21),dict(c,origin=dict(c['origin'],generated={})),dict(c,superclass='p/Fake')):
            with self.assertRaises(ValueError):V.source_methods([changed],methods)
    def test_native_cannot_be_replaced_by_fake_Java_Code_or_wrong_access(self):
        c,methods=self.source()
        for position,value in ((4,'pretend-code'),(8,0x109)):
            changed=list(methods[0]);changed[position]=value
            with self.assertRaisesRegex(ValueError,'declaration'):
                V.source_methods([c],[tuple(changed),*methods[1:]])
    def test_arraycopy_envelope_keeps_pending_errors_and_checks_vm_argv(self):
        body=V.method_body(12,2,2)
        self.assertIn('call boom_class_ensure32',body)
        self.assertIn('cmp DWORD PTR [rcx],0\n    jne boom_m12_native_zero',body)
        self.assertIn('test rdx,rdx\n    jnz boom_m12_native_ready',body)
        self.assertIn('mov r9d,2\n    jmp boom_system_dispatch',body)
        self.assertNotIn('mov DWORD PTR [rcx+4]',body)
    def test_stream_slots_keep_original_field_indices_and_bootstrap_identity(self):
        source=dict(fields=[dict(name='padding',descriptor='I',access=8)]+[dict(name=name,descriptor=desc,access=0x19)
            for name,desc in [('in','Ljava/io/InputStream;'),('out','Ljava/io/PrintStream;'),('err','Ljava/io/PrintStream;')]])
        classes=[dict(id=7,name='java/io/InputStream',origin=dict(loader='bootstrap')),dict(id=9,name='java/io/PrintStream',origin=dict(loader='bootstrap')),
                 dict(id=99,name='java/io/PrintStream',origin=dict(loader='vanilla-application'))]
        slots=V.source_stream_slots(classes,source)
        self.assertEqual([(s['field_index'],s['type_id']) for s in slots],[(1,7),(2,9),(3,9)])
        self.assertIn('QWORD OFFSET boom_s5_1,OFFSET boom_t7',V.stream_pool(5,slots))
        source['fields'][1]['access']=9
        with self.assertRaisesRegex(ValueError,'field/type'):V.source_stream_slots(classes,source)
    def test_stream_envelope_routes_to_setter_without_native_registration_slot(self):
        body=V.method_body(8,3,5)
        self.assertIn('lea r8,boom_batch_system_stream_pool\n    mov r9d,2\n    jmp boom_system_stream_set',body)
        self.assertIn('test rdx,rdx\n    jnz boom_m8_native_ready',body)

if __name__=='__main__':unittest.main()
