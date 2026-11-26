"""Only the original Finalizer declaration may read the VM finalization policy."""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('finalization_policy_tests',ROOT/'scripts/finalization-policy-source.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)
def check(value,message):
    if not value:raise ValueError(message)
def source():
    return (dict(id=3,name='java/lang/ref/Finalizer',access=0x30,method_ids=[8],
        fields=[dict(name='ENABLED',descriptor='Z',access=0x18)],
        origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='original')),
        [dict(name='isFinalizationEnabled',descriptor='()Z',access=0x10a,code=None)])


class FinalizationPolicyTests(unittest.TestCase):
    def bind(self,owner,raw):return M.contracts(owner,raw,SimpleNamespace(check=check))
    def test_original_native_identity_and_configuration_scope(self):
        row,=self.bind(*source())
        self.assertEqual((row['method'],row['access'],row['operation']),(8,0x10a,0))
        self.assertTrue(M.POLICY['query_only'])
        self.assertFalse(M.POLICY['finalizer_registration_implemented'])
    def test_substituted_owner_is_rejected(self):
        owner,raw=source()
        for change in [dict(loader='application'),dict(source_id='library:spoof'),dict(generated={'mod':True})]:
            bad=copy.deepcopy(owner);bad['origin'].update(change)
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'original bootstrap'):self.bind(bad,raw)
    def test_changed_enabled_field_is_rejected(self):
        for change in [dict(descriptor='I'),dict(access=0x8)]:
            owner,raw=source();owner['fields'][0].update(change)
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'ENABLED field'):self.bind(owner,raw)
    def test_changed_native_flags_or_Java_body_is_rejected(self):
        for change in [dict(access=0x102),dict(access=0x109),dict(code=(b'\x04\xac',1,0))]:
            owner,raw=source();raw[0].update(change)
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'private static native'):self.bind(owner,raw)


if __name__=='__main__':unittest.main()
