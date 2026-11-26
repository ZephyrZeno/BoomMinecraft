"""Reject silent-success and source-identity mistakes in diagnostic images."""
import copy
import importlib.util
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location('diagnostic_model',Path(__file__).resolve().parents[1]/'scripts/diagnostic-closure.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)


def frontier(ready=True):
    return dict(kind='unselected_method' if ready else 'method',symbol='boom_m10',reason='test',binding=None,class_id=1,source_sha256='f'*64,
                method=dict(id=10,name='run',descriptor='()V',code_sha256='a'*64 if ready else None,stage='assembly_emitted_unlinked' if ready else 'declaration',assembly_emitted=ready,assembly_unit=0 if ready else None))


class DiagnosticVerifierTests(unittest.TestCase):
    def test_lazy_and_unavailable_methods_stay_distinct(self):
        self.assertEqual(M.rows([frontier()])[0]['category'],1)
        self.assertEqual(M.rows([frontier(False)])[0]['category'],2)

    def test_forged_identity_and_availability_are_rejected(self):
        for key,value in [('symbol','boom_m11'),('kind','method')]:
            f=frontier();f[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):M.rows([f])

    def test_missing_data_is_never_replaced_by_a_callable_stop(self):
        for symbol in ['1','boom_class1','boom_s1_0','boom_layout1','arbitrary_function']:
            f=frontier();f['symbol']=symbol
            with self.subTest(symbol=symbol),self.assertRaises(ValueError):M.rows([f])

    def test_asm_uses_failure_record_and_bounded_byte_declarations(self):
        text=M.body(M.rows([frontier()]))
        self.assertIn('jmp boom_diagnostic_stop',text)
        self.assertIn('mov DWORD PTR [rcx],0B001h',text)
        self.assertIn('lock cmpxchg',text)
        for line in text.splitlines():
            if line.startswith(' BYTE '):self.assertLessEqual(line.count(',')+1,16)

    def test_legacy_runtime_data_is_not_filled_by_a_fake_pool(self):
        b='boom_m10_body PROC\n lea rdx,boom_mirror_pool\n call boom_real_runtime\n call boom_m12\n boom_m10_body ENDP\n'
        self.assertEqual(M.missing_symbols(b,{'boom_real_runtime'},{}),['boom_mirror_pool'])
        f=frontier();f.update(kind='abi_dependency',unprovided_symbols=['boom_mirror_pool'])
        self.assertEqual(M.rows([f])[0]['category'],4)


if __name__=='__main__':unittest.main()
