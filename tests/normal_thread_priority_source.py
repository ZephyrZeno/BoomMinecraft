"""Protect the original private native binding against source/ABI substitution."""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('thread_priority_contract_tests',ROOT/'scripts/normal-thread-priority-source.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)


def check(value,message):
    if not value:raise ValueError(message)


def source():
    return (dict(id=5,name='java/lang/Thread',method_ids=[10],
        origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='original')),
        [dict(name='setPriority0',descriptor='(I)V',access=0x102,code=None)])


class ThreadPriorityContractTests(unittest.TestCase):
    def bind(self,owner,raw):return M.contracts(owner,raw,SimpleNamespace(check=check))

    def test_retains_original_private_native_identity(self):
        row,=self.bind(*source())
        self.assertEqual((row['method'],row['access'],row['operation'],row['class_sha256']),(10,0x102,0,'original'))

    def test_substituted_or_transformed_owner_is_rejected(self):
        owner,raw=source()
        for change in [dict(loader='application'),dict(source_id='library:spoof'),dict(generated={'mod':True})]:
            bad=copy.deepcopy(owner);bad['origin'].update(change)
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'original bootstrap'):
                self.bind(bad,raw)

    def test_changed_native_flags_or_Java_body_is_rejected(self):
        for change in [dict(access=0x101),dict(access=0x10a),dict(code=(b'\xb1',0,2))]:
            owner,raw=source();raw[0].update(change)
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'private native'):
                self.bind(owner,raw)

    def test_missing_or_ambiguous_native_is_rejected(self):
        owner,raw=source()
        with self.assertRaisesRegex(ValueError,'original bootstrap'):self.bind(owner,[])
        owner['method_ids'].append(11);raw.append(copy.deepcopy(raw[0]))
        with self.assertRaisesRegex(ValueError,'private native'):self.bind(owner,raw)


if __name__=='__main__':unittest.main()
