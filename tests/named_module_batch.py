"""Current-source JCLS lineage tests over immutable real source and COFF inputs."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT/'.boom/named-module-batches/v148-jdwp-production-b'


def load(name):
    spec = importlib.util.spec_from_file_location('named_test_' + name, ROOT/'scripts'/(name+'.py'))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


N, C, H = (load(name) for name in ('refresh-named-module-batch', 'verify-batch-classes', 'closure-batch-artifacts'))


def current_fixture():
    if not (BATCH/N.PROOF).is_file():return False
    return N.S.read(BATCH/N.PROOF)['tools'] == N.tools()


@unittest.skipUnless(current_fixture(), 'Requires the immutable v148 fixture with matching current source hashes')
class NamedModuleSourceAndCOFFTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.summary = N.S.read(BATCH/'summary.json')
        resolve, cls.scope = N.source_contract(BATCH, cls.summary)
        cls.resolve = staticmethod(resolve)
        cls.plan = Path(cls.scope['parent']['plan']['path']).parent
        cls.parent = N.S.read(cls.scope['parent']['summary']['path'])
        cls.old = Path(cls.parent['class_literals']['units'][0]['object']['path'])
        cls.new = Path(cls.summary['class_literals']['units'][0]['object']['path'])
        cls.data = cls.new.read_bytes()
        cls.headers = {}
        for i in range(struct.unpack_from('<H', cls.data, 2)[0]):
            at = 20+i*40
            cls.headers[cls.data[at:at+8].rstrip(b'\0').decode()] = at
        target = ROOT/'.boom/named-module-tests'
        target.mkdir(exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=target)
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)

    def class_rejection(self, summary):
        with self.assertRaisesRegex(ValueError, 'Normal Class layout/loader/module source differs'):
            C.verify(BATCH, summary, self.plan, [], None, set(), self.resolve,
                     N.A.coff_symbols, N.A.file_digest)

    def test_source_verifier_rejects_fake_module(self):
        changed = deepcopy(self.summary)
        changed['class_literals']['modules'][-1]['name'] = 'jdk.fake.empty'
        self.class_rejection(changed)

    def test_source_verifier_rejects_wrong_defining_loader(self):
        changed = deepcopy(self.summary)
        changed['class_literals']['modules'][-1]['loader'] = 0
        self.class_rejection(changed)

    def test_source_verifier_rejects_moved_old_boot_slot(self):
        changed = deepcopy(self.summary)
        rows = changed['class_literals']['modules']
        rows[63], rows[64] = rows[64], rows[63]
        rows[63]['id'], rows[64]['id'] = 63, 64
        self.class_rejection(changed)

    def test_lineage_rejects_other_COFF_replacement(self):
        changed = deepcopy(self.summary)
        changed['shards'][0]['units'][0]['object'] = self.summary['class_literals']['units'][0]['object']
        with self.assertRaisesRegex(ValueError, 'outside the one JCLS unit'):
            N.source_contract(BATCH, changed, self.plan)

    def test_instruction_and_relocations_cannot_be_rewritten(self):
        at = self.headers['.text$mn']
        _, code, relocation = struct.unpack_from('<III', self.data, at+16)
        for name, offset in [('instruction', code), ('relocation_target', relocation+4)]:
            with self.subTest(kind=name):
                data = bytearray(self.data)
                data[offset] ^= 1
                path = self.directory/(name+'.obj')
                path.write_bytes(data)
                with self.assertRaisesRegex(ValueError, 'instructions, unwind, complete code relocations'):
                    N.binary_equivalence(self.old, path, self.parent['class_literals'], self.summary['class_literals'])

    def test_GC_count_and_loader_table_are_physically_checked(self):
        pointer = struct.unpack_from('<I', self.data, self.headers['.rdata']+20)[0]
        for name, offset in [('root_count', pointer), ('new_loader', pointer+8+64*4)]:
            with self.subTest(kind=name):
                data = bytearray(self.data)
                data[offset] ^= 1
                path = self.directory/(name+'.obj')
                path.write_bytes(data)
                with self.assertRaisesRegex(ValueError, 'Physical root count or loader-key table differs'):
                    N.binary_equivalence(self.old, path, self.parent['class_literals'], self.summary['class_literals'])

    def test_symbol_swapping_cannot_redirect_unchanged_relocations(self):
        data = bytearray(self.data)
        _, _, _, table, count, _, _ = struct.unpack_from('<HHIIIHH', data)
        strings, index, found = table+18*count, 0, []
        while index < count:
            at = table+18*index
            name = bytes(data[at:at+8])
            _, section, _, storage, auxiliary = struct.unpack_from('<IhHBB', data, at+8)
            if name[:4] == bytes(4):
                start = strings+int.from_bytes(name[4:], 'little')
                value = bytes(data[start:data.index(0, start)]).decode()
            else:
                value = name.rstrip(b'\0').decode()
            if section == 0 and storage == 2 and value in ('boom_t0', 'boom_t1'):
                found.append((at, name))
            index += 1+auxiliary
        self.assertEqual(len(found), 2)
        (a, left), (b, right) = found
        data[a:a+8], data[b:b+8] = right, left
        path = self.directory/'symbol-swap.obj'
        path.write_bytes(data)
        self.assertEqual(N.A.coff_symbols(self.new), N.A.coff_symbols(path))
        with self.assertRaisesRegex(ValueError, 'relocation symbol target or auxiliary contract changed'):
            N.binary_equivalence(self.old, path, self.parent['class_literals'], self.summary['class_literals'])

    def test_resolver_allows_only_certified_unchanged_records_and_new_unit(self):
        summary = self.summary
        old_record = summary['shards'][0]['units'][0]['object']
        self.assertEqual(self.resolve(BATCH, old_record, Path(old_record['path']).parent.name), Path(old_record['path']))
        new_record = summary['class_literals']['units'][0]['object']
        self.assertEqual(self.resolve(BATCH, new_record, 'class-literals'), self.new)
        for record, subdirectory in [
            (self.parent['class_literals']['units'][0]['object'], 'class-literals'),
            (dict(old_record, digest=dict(old_record['digest'], sha256='0'*64)), Path(old_record['path']).parent.name),
            (new_record, 'unsafe-fields'), (new_record, '../class-literals')]:
            with self.subTest(record=record['path'], module=subdirectory), self.assertRaises(ValueError):
                self.resolve(BATCH, record, subdirectory)
        with self.assertRaisesRegex(ValueError, 'Unexpected named-module source root'):
            self.resolve(BATCH.parent, new_record, 'class-literals')

    def test_every_parent_receipt_field_and_named_lineage_is_required(self):
        parent = N.S.read(self.scope['parent']['verification']['path'])
        full = dict(parent, named_module_derivation=self.scope)
        N.check_full_receipt(full, parent, self.scope)
        variants = []
        changed = deepcopy(full);changed['frames']['verified'] = False;variants.append(changed)
        changed = deepcopy(full);changed.pop('unsafe_fields');variants.append(changed)
        changed = deepcopy(full);changed['linked'] = True;variants.append(changed)
        changed = deepcopy(full);changed.pop('named_module_derivation');variants.append(changed)
        changed = deepcopy(full);changed['named_module_derivation']['appended'][0]['loader'] = 0;variants.append(changed)
        for changed in variants:
            with self.subTest(keys=list(changed)), self.assertRaisesRegex(ValueError, 'complete independently verified parent coverage'):
                N.check_full_receipt(changed, parent, self.scope)

    def test_wrapped_resolver_preserves_original_VM_image_home(self):
        wrapped = H.source_records(self.summary, self.resolve)
        self.assertEqual(wrapped.verified_original_vm_image_home, self.resolve.verified_original_vm_image_home)
        with self.assertRaisesRegex(ValueError, 'absent from certified source summary'):
            wrapped(BATCH, self.parent['class_literals']['units'][0]['object'], 'class-literals')

    def test_missing_or_conflicting_named_derivation_is_rejected(self):
        directory = self.directory/'unrecognized'
        directory.mkdir(exist_ok=True)
        (directory/'verification.json').write_text(json.dumps({'named_module_derivation': {}}))
        with self.assertRaisesRegex(ValueError, 'Missing source batch derivation'):
            H.configure(SimpleNamespace(), directory, {})
        (directory/'named-module-derivation.json').write_text('{}')
        (directory/'boot-unnamed-derivation.json').write_text('{}')
        with self.assertRaisesRegex(ValueError, 'Conflicting sparse derivation kinds'):
            H.configure(SimpleNamespace(), directory, {})


if __name__ == '__main__':
    unittest.main()
