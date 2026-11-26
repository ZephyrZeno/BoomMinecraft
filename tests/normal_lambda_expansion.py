"""Small generated-class semantics fixtures, never original-input/runtime proof."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('lambda_fixture_verifier',ROOT/'scripts/verify-normal-lambda-expansion.py')
V=importlib.util.module_from_spec(spec);spec.loader.exec_module(V)
C=V.C;S=C.S


class GeneratedLambdaSemantics(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(dir=S.ART,prefix='lambda-unit-')
        self.root=Path(self.directory.name).resolve();self.assertTrue(self.root.is_relative_to(S.ART))
        self.addCleanup(self.directory.cleanup)

    def plan(self,captures=(),result='Ljava/lang/String;',sam_result='V'):
        sam='(Ljava/lang/Object;)'+sam_result
        return dict(generated_name='example/Host$$BoomNormalLambda$0001',interface=dict(name='example/Function'),
            captures=list(captures),sam_name='accept',sam_descriptor=sam,sam_arguments=['Ljava/lang/Object;'],sam_result=sam_result,
            instantiated_descriptor='(Ljava/lang/String;)'+sam_result,instantiated_arguments=['Ljava/lang/String;'],instantiated_result=sam_result,
            implementation=dict(owner='example/Host',name='validate',descriptor='('+''.join(captures)+'Ljava/lang/String;)'+result,
                reference_kind=6,interface=False),implementation_result=result,
            factory_descriptor='('+''.join(captures)+')Lexample/Function;')

    def record(self,blob):
        file=self.root/'generated.class';file.write_bytes(blob);raw=C.I.Source(blob)
        return dict(class_file=S.artifact(file),methods=[dict(code_length=len(raw.code(m)['bytes']),
            code_sha256=C.hashlib.sha256(raw.code(m)['bytes']).hexdigest()) for m in raw.methods])

    def test_reference_cast_and_void_result_discard(self):
        plan=self.plan();record=self.record(C.generated_class(plan));proof=V.class_semantics(record,plan)
        self.assertTrue(proof['independent_bytecode_semantics_verified'])
        raw=C.I.Source(Path(record['class_file']['path']).read_bytes());steps=V.code_steps(raw,raw.methods[-1])
        self.assertIn((0xc0,'java/lang/String'),steps);self.assertIn((0x57,),steps)

    def test_reference_capture_order_and_private_final_fields(self):
        plan=self.plan(('Ljava/lang/Object;','Ljava/lang/String;'));record=self.record(C.generated_class(plan))
        self.assertEqual(V.class_semantics(record,plan)['captured_references'],2)
        raw=C.I.Source(Path(record['class_file']['path']).read_bytes());self.assertEqual([f['access'] for f in raw.fields],[0x1012,0x1012])

    def test_wide_implementation_result_discard_uses_pop2(self):
        plan=self.plan(result='J');record=self.record(C.generated_class(plan));V.class_semantics(record,plan)
        raw=C.I.Source(Path(record['class_file']['path']).read_bytes());self.assertIn((0x58,),V.code_steps(raw,raw.methods[-1]))

    def test_exact_primitive_result_uses_ireturn(self):
        plan=self.plan(result='Z',sam_result='Z');record=self.record(C.generated_class(plan));V.class_semantics(record,plan)
        raw=C.I.Source(Path(record['class_file']['path']).read_bytes());self.assertEqual(V.code_steps(raw,raw.methods[-1])[-1],(0xac,))

    def test_resealed_cast_constant_tamper_is_rejected(self):
        plan=self.plan();blob=C.generated_class(plan)
        before=b'\x01\x00\x10java/lang/String';after=b'\x01\x00\x10java/lang/Object'
        self.assertEqual(blob.count(before),1);record=self.record(blob.replace(before,after))
        with self.assertRaisesRegex(ValueError,'capture order, casts'):V.class_semantics(record,plan)

    def test_resealed_implementation_name_tamper_is_rejected(self):
        plan=self.plan();blob=C.generated_class(plan);before=b'\x01\x00\x08validate';after=b'\x01\x00\x08identity'
        self.assertEqual(blob.count(before),1);record=self.record(blob.replace(before,after))
        with self.assertRaisesRegex(ValueError,'capture order, casts'):V.class_semantics(record,plan)

    def test_changed_capture_contract_is_rejected(self):
        plan=self.plan(('Ljava/lang/Object;','Ljava/lang/String;'));record=self.record(C.generated_class(plan))
        other=copy.deepcopy(plan);other['captures'].reverse()
        with self.assertRaisesRegex(ValueError,'capture fields'):V.class_semantics(record,other)

    def test_hidden_runtime_name_is_nonbinary_and_stable(self):
        plan=self.plan();first=C.runtime_class_name(plan,1234)
        self.assertEqual(first,'example.Host$$BoomNormalLambda$0001/0x00000000000004d2')
        self.assertNotEqual(first,C.runtime_class_name(plan,1235))

    def test_hidden_self_references_share_the_this_class_constant(self):
        plan=self.plan();raw=C.I.Source(C.generated_class(plan))
        entries=[i for i,v in enumerate(raw.cp) if v is not None and v[0]==7 and raw.class_name(i)==plan['generated_name']]
        self.assertEqual(len(entries),1)


if __name__=='__main__':unittest.main()
