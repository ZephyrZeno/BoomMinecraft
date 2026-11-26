"""Protect the VM notification binding from substituted bootstrap declarations."""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('object_notification_tests',ROOT/'scripts/object-notification-source.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)
def check(value,message):
    if not value:raise ValueError(message)
def source():
    return (dict(id=3,name='java/lang/Object',access=0x21,method_ids=[8,9],
        origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='original')),
        [dict(name=n,descriptor='()V',access=0x111,code=None) for n in ('notify','notifyAll')])


class ObjectNotificationTests(unittest.TestCase):
    def bind(self,owner,raw):return M.contracts(owner,raw,SimpleNamespace(check=check))
    def test_original_final_native_identities_and_empty_wait_scope(self):
        rows=self.bind(*source())
        self.assertEqual([(r['method'],r['access'],r['operation']) for r in rows],[(8,0x111,0),(9,0x111,1)])
        self.assertFalse(M.POLICY['Object_wait_implemented'])
    def test_substituted_owner_is_rejected(self):
        owner,raw=source()
        for change in [dict(loader='application'),dict(source_id='library:spoof'),dict(generated={'mod':True})]:
            bad=copy.deepcopy(owner);bad['origin'].update(change)
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'original bootstrap'):self.bind(bad,raw)
    def test_changed_final_native_flags_or_body_is_rejected(self):
        for change in [dict(access=0x101),dict(access=0x119),dict(code=(b'\xb1',0,1))]:
            owner,raw=source();raw[1].update(change)
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'public final native'):self.bind(owner,raw)
    def test_missing_or_ambiguous_original_declaration_is_rejected(self):
        owner,raw=source()
        with self.assertRaisesRegex(ValueError,'original bootstrap'):self.bind(owner,raw[:-1])
        owner['method_ids'].append(10);raw.append(copy.deepcopy(raw[0]))
        with self.assertRaisesRegex(ValueError,'public final native'):self.bind(owner,raw)


if __name__=='__main__':unittest.main()
