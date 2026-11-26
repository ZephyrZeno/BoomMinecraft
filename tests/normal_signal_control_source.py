"""Signal VM callbacks must retain their original loader, access and Java Code."""
import copy
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('signal_control_contract_tests',
    Path(__file__).resolve().parents[1]/'scripts/normal-signal-control-source.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class Source:
    @staticmethod
    def check(value, message):
        if not value:
            raise ValueError(message)


def original():
    owner = dict(id=7,name='jdk/internal/misc/Signal',method_ids=[90],
                 origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='source'))
    raw = [dict(name='dispatch',descriptor='(I)V',access=0xa,code=(b'\xb1',1,1))]
    return owner,raw


class SignalControlSourceTests(unittest.TestCase):
    def test_retains_original_private_static_java_callback(self):
        row = M.java_contract(*original(),'dispatch','(I)V',0xa,Source)
        self.assertEqual((row['method'],row['class_id'],row['access']),(90,7,0xa))
        self.assertEqual(row['class_sha256'],'source')
        self.assertEqual(len(row['code_sha256']),64)

    def test_application_generated_or_other_library_callbacks_are_rejected(self):
        for delta in [dict(loader='application'),dict(source_id='library'),dict(generated=True)]:
            owner,raw = original();owner['origin'].update(delta)
            with self.subTest(delta=delta),self.assertRaisesRegex(ValueError,'original bootstrap'):
                M.java_contract(owner,raw,'dispatch','(I)V',0xa,Source)

    def test_changed_access_native_or_abstract_callback_is_rejected(self):
        for access in [1,2,8,0x10a,0x40a]:
            owner,raw = original();raw[0]['access']=access
            with self.subTest(access=access),self.assertRaisesRegex(ValueError,'flags/Code'):
                M.java_contract(owner,raw,'dispatch','(I)V',0xa,Source)

    def test_callback_without_original_java_code_is_rejected(self):
        owner,raw = original();raw[0]['code']=None
        with self.assertRaisesRegex(ValueError,'flags/Code'):
            M.java_contract(owner,raw,'dispatch','(I)V',0xa,Source)

    def test_truncated_inventory_is_rejected(self):
        owner,raw = original();owner['method_ids'].append(91)
        with self.assertRaisesRegex(ValueError,'original bootstrap'):
            M.java_contract(owner,raw,'dispatch','(I)V',0xa,Source)

    def test_duplicate_signature_cannot_select_an_arbitrary_source_callback(self):
        owner,raw = original();owner['method_ids'].append(91);raw.append(copy.deepcopy(raw[0]))
        with self.assertRaisesRegex(ValueError,'flags/Code'):
            M.java_contract(owner,raw,'dispatch','(I)V',0xa,Source)


if __name__ == '__main__':
    unittest.main()
