"""Only original instance Java callbacks can participate in platform start."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('thread_start_contract_tests', ROOT/'scripts/normal-thread-start-source.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def check(value, message):
    if not value:
        raise ValueError(message)


def source():
    owner = dict(id=5, name='java/lang/Thread', method_ids=[10, 11, 12, 13, 14],
                 origin=dict(loader='bootstrap', source_id='jdk:java.base', sha256='original'))
    raw = [dict(name='start0', descriptor='()V', access=0x102, code=None)]
    for name, descriptor, access in [('run', '()V', 1), ('exit', '()V', 2),
            ('dispatchUncaughtException', '(Ljava/lang/Throwable;)V', 0),
            ('runWith', '(Ljava/lang/Object;Ljava/lang/Runnable;)V', 0x10)]:
        raw.append(dict(name=name, descriptor=descriptor, access=access, code=(b'\xb1', 1, 3)))
    return owner, raw


class ThreadStartContractTests(unittest.TestCase):
    def test_binds_native_start_and_retains_original_callback_identities(self):
        methods, calls = M.contracts(*source(), check)
        self.assertEqual((methods[0]['method'], methods[0]['access'], methods[0]['operation']), (10, 0x102, 0))
        self.assertEqual([c['method'] for c in calls], [11, 12, 13, 14])
        self.assertTrue(all(c['code_sha256'] and c['class_sha256'] == 'original' for c in calls))

    def test_generated_application_or_library_classes_cannot_claim_thread_start(self):
        owner, raw = source()
        for change in [dict(loader='application'), dict(source_id='library:spoof'), dict(generated={'mod': True})]:
            bad = copy.deepcopy(owner)
            bad['origin'].update(change)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'original bootstrap'):
                M.contracts(bad, raw, check)

    def test_native_with_a_java_body_is_rejected(self):
        owner, raw = source()
        raw[0]['code'] = (b'\xb1', 0, 1)
        with self.assertRaisesRegex(ValueError, 'native flags/Code'):
            M.contracts(owner, raw, check)

    def test_public_or_static_start0_is_not_the_original_private_native(self):
        for access in [0x101, 0x10a]:
            owner, raw = source()
            raw[0]['access'] = access
            with self.subTest(access=access), self.assertRaisesRegex(ValueError, 'native flags/Code'):
                M.contracts(owner, raw, check)

    def test_native_abstract_or_static_callbacks_are_not_accepted(self):
        for flag in [8, 0x100, 0x400]:
            owner, raw = source()
            raw[1]['access'] |= flag
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, 'instance Java Code'):
                M.contracts(owner, raw, check)

    def test_callbacks_without_original_code_are_rejected(self):
        owner, raw = source()
        raw[2]['code'] = None
        with self.assertRaisesRegex(ValueError, 'instance Java Code'):
            M.contracts(owner, raw, check)

    def test_changed_callback_visibility_does_not_silently_change_vm_access(self):
        owner, raw = source()
        raw[3]['access'] = 2
        with self.assertRaisesRegex(ValueError, 'upcall access'):
            M.contracts(owner, raw, check)

    def test_truncated_original_inventory_is_rejected(self):
        owner, raw = source()
        with self.assertRaisesRegex(ValueError, 'original inventory'):
            M.contracts(owner, raw[:-1], check)


if __name__ == '__main__':
    unittest.main()
