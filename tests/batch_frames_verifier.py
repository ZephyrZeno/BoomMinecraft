"""Check annotation trust boundaries and malformed source-byte rejection."""
import importlib.util
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

SPEC=importlib.util.spec_from_file_location('frame_verifier_tests',Path(__file__).resolve().parents[1]/'scripts/verify-batch-frames.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)


def original_class(annotation=b'\x00\x01\x00\x06\x00\x00'):
    strings=['Example','java/lang/Object','query','()V','RuntimeVisibleAnnotations','Ljdk/internal/reflect/CallerSensitive;']
    cp=[b'\x01'+struct.pack('>H',len(s))+s.encode() for s in strings]
    cp += [b'\x07\x00\x01',b'\x07\x00\x02']
    return (bytes.fromhex('cafebabe00000041')+struct.pack('>H',9)+b''.join(cp)+
            struct.pack('>HHHHHH',0x21,7,8,0,0,1)+
            struct.pack('>HHHHHI',0x109,3,4,1,5,len(annotation))+annotation+b'\x00\x00')


class FrameVerifierTests(unittest.TestCase):
    def test_caller_annotation_is_read_from_original_method_attribute(self):
        owner,methods=M.original_methods(original_class())
        self.assertEqual(owner,'Example')
        self.assertEqual(methods[0]['annotations'],['Ljdk/internal/reflect/CallerSensitive;'])
        self.assertIsNone(methods[0]['code'])
        self.assertEqual(M.flags(owner,methods[0],True,False,False),40)

    def test_annotation_name_does_not_grant_application_caller_privilege(self):
        owner,methods=M.original_methods(original_class())
        self.assertEqual(M.flags(owner,methods[0],False,False,False),32)

    def test_hidden_annotation_alone_does_not_skip_security_stack_walk(self):
        method=dict(name='query',descriptor='()V',access=1,annotations=['Ljdk/internal/vm/annotation/Hidden;'])
        self.assertEqual(M.flags('Example',method,True,False,False),16)
        method['annotations'].append('Ljava/lang/invoke/LambdaForm$Compiled;')
        self.assertEqual(M.flags('Example',method,True,False,False),80)

    def test_truncated_or_unknown_annotation_values_are_rejected(self):
        for data in [original_class()[:-1],original_class(b'\x00\x01\x00\x06\x00\x01\x00\x03?')]:
            with self.subTest(data=data[-12:]),self.assertRaises(ValueError): M.original_methods(data)

    def test_original_modified_utf8_preserves_null_and_supplementary_name(self):
        self.assertEqual(M.modified_utf8(b'A\xc0\x80\xed\xa0\xbd\xed\xb8\x80'),'A\0\U0001f600')

    def test_wrong_runtime_kernel_is_rejected_before_source_execution(self):
        spec=importlib.util.spec_from_file_location('frame_runtime_guard',Path(__file__).resolve().parents[1]/'scripts/diagnostic-closure.py')
        guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
        with tempfile.TemporaryDirectory() as directory:
            runtime=Path(directory)/'boom-runtime.dll';runtime.write_bytes(b'explicit fixture')
            meta=dict(sha256=hashlib.sha256(runtime.read_bytes()).hexdigest(),java_runtime=False,rust_runtime=False,c_runtime=False,sources={'native/runtime/frames.asm':'new'})
            (runtime.parent/'runtime.json').write_text(json.dumps(meta))
            summary=dict(schema=23,frames=dict(kernel_sha256={'native/runtime/frames.asm':'new'}))
            guard.frame_runtime_identity(summary,runtime)
            summary['frames']['kernel_sha256']['native/runtime/frames.asm']='old'
            with self.assertRaisesRegex(ValueError,'kernel ABI differs'):guard.frame_runtime_identity(summary,runtime)

    def test_runtime_receipt_cannot_hide_a_changed_DLL(self):
        spec=importlib.util.spec_from_file_location('frame_runtime_guard_tamper',Path(__file__).resolve().parents[1]/'scripts/diagnostic-closure.py')
        guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
        with tempfile.TemporaryDirectory() as directory:
            runtime=Path(directory)/'boom-runtime.dll';runtime.write_bytes(b'changed')
            (runtime.parent/'runtime.json').write_text(json.dumps(dict(sha256='old')))
            with self.assertRaisesRegex(ValueError,'DLL differs'):guard.frame_runtime_identity(dict(schema=23),runtime)


if __name__=='__main__':unittest.main()
