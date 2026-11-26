"""Reject false native/source/index/profile contracts before linking properties."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location('properties_verifier', Path(__file__).resolve().parents[1]/'scripts/verify-batch-properties.py')
M = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(M)


def source():
    cls = dict(id=1, name=M.OWNER, origin=dict(loader='bootstrap', source_id='jdk:java.base', sha256='original'), method_ids=[10, 11])
    fields = [dict(name=f'_slot{i}_NDX', access=0x1a, descriptor='I', constant_value=i+1) for i in range(39)]
    fields.append(dict(name='FIXED_LENGTH', access=0x1a, descriptor='I', constant_value=40))
    info = {1: dict(source_sha256='original', initializers=[], fields=fields,
                    constants={str(i+1): dict(Int=i) for i in range(40)})}
    inventory = {10+i: (1, name, '()[Ljava/lang/String;', 'original', None, 0, 0, 0, 0x10a)
                 for i, name in enumerate(('platformProperties', 'vmProperties'))}
    return [cls], inventory, info


class PropertyVerifierTests(unittest.TestCase):
    def test_normal_native_declarations_are_distinct_from_Java_Code(self):
        classes, inventory, inputs = source()
        _, indices, methods = M.source_contract(classes, inventory, inputs)
        self.assertEqual((len(indices), [m['operation'] for m in methods]), (39, [0, 1]))
        row = list(inventory[10]); row[4] = 'unexpected Java Code'; inventory[10] = tuple(row)
        with self.assertRaisesRegex(ValueError, 'signature/access/Code'):
            M.source_contract(classes, inventory, inputs)

    def test_loader_generated_origin_and_initializer_cannot_be_silently_replaced(self):
        for mutation in ('loader', 'generated', 'initializer'):
            classes, inventory, inputs = source()
            if mutation == 'loader': classes[0]['origin']['loader'] = 'application'
            if mutation == 'generated': classes[0]['origin']['generated'] = dict(generator='substitute')
            if mutation == 'initializer': inputs[1]['initializers'] = [dict(id=12)]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                M.source_contract(classes, inventory, inputs)

    def test_duplicate_index_or_noninteger_constant_is_not_a_valid_schema(self):
        classes, inventory, inputs = source()
        inputs[1]['constants']['2'] = dict(Int=0)
        with self.assertRaisesRegex(ValueError, 'indexed schema'):
            M.source_contract(classes, inventory, inputs)
        inputs[1]['constants']['2'] = dict(Long=1)
        with self.assertRaisesRegex(ValueError, 'integer'):
            M.source_contract(classes, inventory, inputs)

    def test_locked_JDK21_fields_do_not_inherit_newer_JDK_property_slots(self):
        self.assertEqual(M.query('_file_encoding_NDX'), (9, 0, None))
        self.assertEqual(M.query('_stdout_encoding_NDX'), (10, 0, None))
        for name in ('_stdin_encoding_NDX', '_native_encoding_NDX', '_https_nonProxyHosts_NDX'):
            with self.subTest(name=name), self.assertRaises(ValueError): M.query(name)

    def test_UTF16_sort_and_java_hash_preserve_supplementary_characters(self):
        _, _, texts, _ = M.model({'_file_separator_NDX': 0}, {'key': '\U0001f600'})
        found = next(t for t in texts if t['utf16'] == [0xd83d, 0xde00])
        self.assertEqual(found['java_hash'], 1772899)
        self.assertEqual([t['utf16'] for t in texts], sorted(t['utf16'] for t in texts))

    def test_VM_profile_uses_truthful_assembly_identity_and_rejects_unbound_overrides(self):
        with tempfile.TemporaryDirectory() as root:
            profile = dict(schema=1, java_home=root, class_path='classes', library_path='natives', properties=[])
            values = M.vm_values(profile, root)
            self.assertEqual(values['java.vm.name'], 'BoomMinecraft Assembly VM')
            self.assertEqual(values['java.vm.specification.version'], '21')
            profile['properties'] = [dict(key='java.vm.name', value='HotSpot')]
            with self.assertRaisesRegex(ValueError, 'default VM profile'): M.vm_values(profile, root)

    def test_VM_profile_rejects_wrong_output_and_NUL_configuration(self):
        with tempfile.TemporaryDirectory() as root:
            profile = dict(schema=1, java_home=root, class_path='bad\0path', library_path='natives', properties=[])
            with self.assertRaisesRegex(ValueError, 'profile text'): M.vm_values(profile, root)
            profile['class_path'] = 'classes'; profile['java_home'] = str(Path(root)/'other')
            with self.assertRaisesRegex(ValueError, 'java.home'): M.vm_values(profile, root)


if __name__ == '__main__': unittest.main()
