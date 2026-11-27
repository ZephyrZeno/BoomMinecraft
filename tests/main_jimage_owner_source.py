"""Fail-closed source bindings and exact native-entry lifecycle deltas."""
import copy
import importlib.util
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('test_main_jimage_owner_source', ROOT/'scripts/main-jimage-owner-source.py')
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class MainJimageOwnerSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = (ROOT/M.TEMPLATE).read_text(encoding='utf-8')
        cls.workspace = next(parent for parent in Path(__file__).resolve().parents
            if (parent/'native/entry/vm_process.asm.inc').exists())
        cls.original_process = (cls.workspace/'native/entry/vm_process.asm.inc').read_text(encoding='utf-8')

    def model(self):
        key = 'Z:\\BoomFixtures\\runtime-运行时-😀\\lib\\modules'
        return dict(schema=1,kind='native_main_jimage_process_owner_source',
            exact_modules_key=key,exact_modules_UTF16=M.units(key),expected_modules_bytes=456789,
            original_unload_native=dict(method=700003),module_literal_ids=dict(jimage=41,nio=63,net=87),
            report_bytes=256,report_abi=1,exports=sorted(M.EXPORTS))

    def test_complete_UTF16_key_keeps_surrogate_pair_and_exact_length(self):
        model = self.model()
        text = M.render(model,self.template)
        body = text.partition('boom_main_jimage_modules_key LABEL WORD\n')[2].partition('\n WORD 0\n')[0]
        values = [int(token.strip().removeprefix('0').removesuffix('h') or '0',16)
            for line in body.splitlines() for token in line.removeprefix(' WORD ').split(',')]
        self.assertEqual(values,model['exact_modules_UTF16'])
        self.assertEqual(len(values),len(model['exact_modules_key'])+1)
        self.assertIn(' mov QWORD PTR [mj_bootstrap_job+16],'+str(len(values))+'\n',text)

    def test_unload_method_and_three_literal_IDs_are_all_dynamic(self):
        model = self.model()
        first = M.render(model,self.template)
        model['original_unload_native']['method'] = 900007
        model['module_literal_ids'] = dict(jimage=123,nio=456,net=789)
        second = M.render(model,self.template)
        self.assertNotIn('boom_m700003',second)
        self.assertEqual(second.count('boom_m900007'),2)
        for value,kind in ((123,3),(456,2),(789,1)):
            self.assertIn(f' DWORD {value},{kind}\n',second)
        self.assertNotEqual(first,second)

    def test_inconsistent_property_key_UTF16_is_rejected(self):
        model = self.model()
        model['exact_modules_UTF16'][-1] ^= 1
        with self.assertRaisesRegex(ValueError,'source model differs'):
            M.render(model,self.template)

    def test_unknown_template_binding_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'Unknown or missing'):
            M.render(self.model(),self.template+'\n@UNDECLARED_RUNTIME_INPUT@\n')

    def test_six_native_process_edits_recover_exact_original(self):
        derived,edits = M.derive_process(self.original_process)
        self.assertEqual(len(edits),6)
        self.assertTrue(any(row['name']=='retain_all_VM_memory_if_trace_release_failed' for row in edits))
        for row in reversed(edits):
            self.assertEqual(derived.count(row['after']),1)
            derived = derived.replace(row['after'],row['before'],1)
        self.assertEqual(derived,self.original_process)

    def test_missing_original_failure_boundary_cannot_be_guessed(self):
        changed = self.original_process.replace('vpe_frame_error:\n','vpe_frame_error_changed:\n',1)
        with self.assertRaisesRegex(ValueError,'exact standard VM anchor'):
            M.derive_process(changed)

    def test_unload_cleanup_keeps_original_Context_as_read_only_input(self):
        text = M.render(self.model(),self.template)
        body = text.partition('boom_main_jimage_unload_modules PROC FRAME\n')[2].partition('boom_main_jimage_unload_modules ENDP')[0]
        self.assertIn(' lea rcx,boom_main_jimage_report+160\n',body)
        self.assertIn(' lea rcx,boom_trace_pool\n lea rdx,boom_main_jimage_report+160\n call boom_trace_head\n',body)
        self.assertNotRegex(body,r'(?m)^ (?:mov|xor|and|or|inc|dec|xchg|add|sub) (?:QWORD|DWORD|WORD|BYTE) PTR \[rbx(?:\+[^\]]*)?\],')
        self.assertIn(' cmp rax,QWORD PTR [r10+rcx*8]\n jne mju_context_failed\n',body)


if __name__ == '__main__':
    unittest.main()
