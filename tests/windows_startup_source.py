"""Windows process mode bindings reject transformed or incompatible declarations."""
import importlib.util
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location('windows_startup_contract_tests',
    Path(__file__).resolve().parents[1]/'scripts/windows-startup-source.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)


class Source:
    @staticmethod
    def check(value,message):
        if not value:raise ValueError(message)


def original():
    owner=dict(id=7,name='sun/io/Win32ErrorMode',access=0x21,method_ids=[9],
        origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='original'))
    return owner,[dict(name='setErrorMode',descriptor='(J)J',access=0x10a,code=None)]


class WindowsStartupContractTests(unittest.TestCase):
    def test_preserves_original_private_native_identity(self):
        row=M.contracts(*original(),Source)[0]
        self.assertEqual((row['method'],row['access'],row['operation']),(9,0x10a,0))
        self.assertEqual(row['class_sha256'],'original')

    def test_application_generated_or_other_library_cannot_change_process_mode(self):
        for delta in [dict(loader='application'),dict(generated=True),dict(source_id='library')]:
            owner,raw=original();owner['origin'].update(delta)
            with self.subTest(delta=delta),self.assertRaisesRegex(ValueError,'original bootstrap'):
                M.contracts(owner,raw,Source)

    def test_changed_access_or_descriptor_is_rejected(self):
        for delta in [dict(access=0x109),dict(access=0x101),dict(descriptor='(I)J')]:
            owner,raw=original();raw[0].update(delta)
            with self.subTest(delta=delta),self.assertRaisesRegex(ValueError,'private native'):
                M.contracts(owner,raw,Source)

    def test_native_with_Java_code_is_rejected(self):
        owner,raw=original();raw[0]['code']=(b'\xb1',0,0)
        with self.assertRaisesRegex(ValueError,'private native'):M.contracts(owner,raw,Source)

    def test_new_class_initializer_invalidates_original_contract(self):
        owner,raw=original();owner['method_ids'].append(10);raw.append(dict(name='<clinit>',access=8))
        with self.assertRaisesRegex(ValueError,'no class initializer'):M.contracts(owner,raw,Source)

    def test_additional_native_invalidates_inventory(self):
        owner,raw=original();owner['method_ids'].append(10);raw.append(dict(name='other',access=0x10a))
        with self.assertRaisesRegex(ValueError,'native inventory'):M.contracts(owner,raw,Source)


if __name__=='__main__':unittest.main()
