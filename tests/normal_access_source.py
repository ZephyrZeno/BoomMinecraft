"""Reject forged native declarations, layouts and privileged-frame identities."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('normal_access_contract_tests', ROOT/'scripts/normal-access-source.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def check(value, message):
    if not value:
        raise ValueError(message)


class NormalAccessSourceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=ROOT/'.boom')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        names = ['java/security/AccessController', 'java/security/AccessControlContext',
                 'java/lang/Thread', 'java/security/ProtectionDomain', 'example/Game']
        self.classes = [dict(id=i, name=name, method_ids=[], fields=[],
            origin=dict(loader='application' if i == 4 else 'bootstrap',
                source_id='minecraft:server' if i == 4 else 'jdk:java.base', sha256=str(i)*64))
            for i, name in enumerate(names)]
        self.classes[0]['method_ids'] = list(range(10, 15))
        self.raw = [dict(name=n, descriptor=d, access=a, code=None) for n, d, a in M.SPECS]
        self.raw += [dict(name='executePrivileged', descriptor=d, access=0x0a, code=(b'\xb1', 4, 3))
            for d in ('(Ljava/security/PrivilegedAction;Ljava/security/AccessControlContext;Ljava/lang/Class;)Ljava/lang/Object;',
                      '(Ljava/security/PrivilegedExceptionAction;Ljava/security/AccessControlContext;Ljava/lang/Class;)Ljava/lang/Object;')]
        self.layouts = []
        declarations = {
            1: [('context', '[Ljava/security/ProtectionDomain;', 8, 0),
                ('privilegedContext', 'Ljava/security/AccessControlContext;', 8, 8),
                ('isPrivileged', 'Z', 1, 16), ('isAuthorized', 'Z', 1, 17)],
            2: [('inheritedAccessControlContext', 'Ljava/security/AccessControlContext;', 8, 0)]}
        for owner, fields in declarations.items():
            physical = []
            for i, (name, descriptor, width, offset) in enumerate(fields):
                member = dict(name=name, descriptor=descriptor, access=2)
                self.classes[owner]['fields'].append(member)
                physical.append(dict(member=dict(member, owner=owner, index=i), storage_bytes=width, offset=offset))
            self.layouts.append(dict(class_id=owner, diagnostic=None, source_sha256=str(owner)*64,
                                     candidate=dict(fields=physical)))
        self.types = [dict(id=c['id'], name=c['name'], kind=1, defining_loader=c['origin']['loader'],
                           source_sha256=c['origin']['sha256']) for c in self.classes]
        self.types += [dict(id=5, name='[Ljava/security/ProtectionDomain;', defining_loader='bootstrap',
                            kind=3, parent_component=3), dict(id=6, name='int', kind=0)]
        self.overlay = dict(source=dict(rows=[[10, 40, 0, 0], [11, 32, 0, 0], [12, 96, 0, 0],
                                              [13, 0, 0, 1], [14, 0, 0, 1], [17, 0, 4, 3]]))

    def build(self):
        index = self.root/'types.zip'
        with zipfile.ZipFile(index, 'w') as archive:
            archive.writestr('types.jsonl', ''.join(json.dumps(row)+'\n' for row in self.types))
        layouts = self.root/'layouts.jsonl'
        layouts.write_text(''.join(json.dumps(row)+'\n' for row in self.layouts), encoding='utf-8')
        summary = dict(runtime_metadata=dict(index=dict(path=str(index)), type_capacity=7),
                       class_literals=dict(type_capacity=7), layouts=dict(path=str(layouts)))
        io = SimpleNamespace(check=check, checked=lambda r: Path(r['path']), original_class=lambda *args: b'original')
        with patch.object(M.R, 'original_methods', return_value=(self.classes[0]['name'], self.raw)):
            return M.index(summary, self.classes, self.overlay, io)

    def test_native_ids_and_application_domains_remain_distinct(self):
        result = self.build()
        self.assertEqual([m['method'] for m in result['methods']], [10, 11, 12])
        self.assertEqual(result['domain_bound'], [1, 1, 1, 1, 0, 1, 1])
        self.assertEqual(result['field_offsets'], [0, 8, 16, 17, 0])

    def test_both_original_privileged_overloads_keep_their_real_locals(self):
        result = self.build()
        self.assertEqual(result['original_privileged_method_ids'], [13, 14])
        rows = {r[0]: r for r in result['frame_rows']}
        self.assertEqual(rows[13][2:], [1, -56, 3])
        self.assertEqual(rows[14][2:], [1, -56, 3])
        self.assertEqual(rows[12][2], 4)

    def test_application_interface_requires_an_explicit_protection_domain(self):
        self.types[4]['kind'] = 2
        self.assertEqual(self.build()['domain_bound'][4], 0)

    def test_transformed_bootstrap_interface_does_not_inherit_system_authority(self):
        self.types[4]['kind'] = 2
        self.classes[4]['origin'].update(loader='bootstrap', source_id='jdk:java.base', generated={'transform': 'mod'})
        self.assertEqual(self.build()['domain_bound'][4], 0)

    def test_transformed_or_non_jdk_sources_cannot_claim_vm_authority(self):
        for change in (dict(generated={'transform': 'mod'}), dict(source_id='library:spoof')):
            with self.subTest(change=change):
                original = copy.deepcopy(self.classes[0]['origin'])
                self.classes[0]['origin'].update(change)
                with self.assertRaisesRegex(ValueError, 'original java.base'):
                    self.build()
                self.classes[0]['origin'] = original

    def test_native_with_java_code_is_rejected(self):
        self.raw[0]['code'] = (b'\xb0', 1, 0)
        with self.assertRaisesRegex(ValueError, 'native declaration'):
            self.build()

    def test_changed_native_access_is_rejected(self):
        self.raw[0]['access'] = 0x109
        with self.assertRaisesRegex(ValueError, 'native declaration'):
            self.build()

    def test_duplicate_source_frame_identity_is_rejected(self):
        self.overlay['source']['rows'].append(self.overlay['source']['rows'][0])
        with self.assertRaisesRegex(ValueError, 'Duplicate source frame'):
            self.build()

    def test_missing_privileged_source_frame_is_rejected(self):
        self.overlay['source']['rows'] = [r for r in self.overlay['source']['rows'] if r[0] != 14]
        with self.assertRaisesRegex(ValueError, 'Privileged method or frame'):
            self.build()

    def test_native_frame_cannot_impersonate_original_privileged_java(self):
        self.overlay['source']['rows'][3][1] = 32
        with self.assertRaisesRegex(ValueError, 'original Java body'):
            self.build()

    def test_boolean_layout_width_is_not_guessed(self):
        self.layouts[0]['candidate']['fields'][2]['storage_bytes'] = 4
        with self.assertRaisesRegex(ValueError, 'field width'):
            self.build()

    def test_domain_array_must_have_the_original_component_class(self):
        self.types[5]['parent_component'] = 2
        with self.assertRaisesRegex(ValueError, r'ProtectionDomain\[\] type missing'):
            self.build()


if __name__ == '__main__':
    unittest.main()
