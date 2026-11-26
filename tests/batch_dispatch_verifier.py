"""Source-selection regression cases for the independent dispatch verifier."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('batch_dispatch_verifier', ROOT/'scripts/verify-batch-dispatch.py')
V = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(V)


def source_model():
    classes, methods = [], []
    def add(name, access=1, parent='java/lang/Object', interfaces=(), declarations=()):
        id_ = len(classes); ids = []
        for method_name, flags in declarations:
            ids.append(len(methods)); methods.append((id_, method_name, '()I', 'sha', 'code', 2, 1, 1, flags))
        classes.append(dict(id=id_, name=name, access=access, superclass=parent, interfaces=list(interfaces),
                            fields=[], method_ids=ids, origin=dict(loader='bootstrap', source_id='fixture', sha256='sha')))
        return id_
    add('java/lang/Object', parent='')
    add('p/Root', 0x601, declarations=[('f', 1)])
    add('p/Child', 0x601, interfaces=['p/Root'], declarations=[('f', 1)])
    add('p/Reabstract', 0x601, interfaces=['p/Root'], declarations=[('f', 0x401)])
    add('p/A', interfaces=['p/Root'], declarations=[('f', 1)])
    add('p/B', interfaces=['p/Child'])
    add('p/Missing', interfaces=['p/Reabstract'])
    add('p/Left', 0x601, declarations=[('f', 1)])
    add('p/Conflict', interfaces=['p/Root', 'p/Left'])
    add('p/Hidden', interfaces=['p/Root'], declarations=[('f', 4)])
    add('p/Base', declarations=[('g', 0)])
    add('p/Middle', parent='p/Base', declarations=[('g', 1)])
    add('q/Leaf', parent='p/Middle', declarations=[('g', 1)])
    return V.Model(classes, methods)


class DispatchVerifierTests(unittest.TestCase):
    def test_interface_override_default_reabstract_conflict_and_access(self):
        model = source_model(); root = model.methods[1]['f', '()I']
        self.assertEqual(model.select(4, root, True), (model.methods[4]['f', '()I'], 0))
        self.assertEqual(model.select(5, root, True), (model.methods[2]['f', '()I'], 0))
        self.assertEqual(model.select(6, root, True), (None, 14))
        self.assertEqual(model.select(8, root, True), (None, 13))
        self.assertEqual(model.select(9, root, True), (None, 15))

    def test_package_private_override_can_follow_public_intermediate(self):
        model = source_model(); base = model.methods[10]['g', '()I']
        self.assertEqual(model.select(12, base, False), (model.methods[12]['g', '()I'], 0))

    def test_requests_merge_methods_without_losing_site_constraints(self):
        requests = V.Requests()
        binding = dict(label='boom_batch_call_4_7_185', kind='virtual_dispatch', caller_class=4, caller_method=10,
                       constant=7, opcode=185, descriptor='()I', resolved_method=2,
                       dispatch=dict(symbolic_owner=1, receiver_constraint=4, resolved_owner=1, resolved_index=0, interface=True))
        requests.observe(4, 'sha', 10, binding)
        requests.observe(4, 'sha', 11, dict(binding, caller_method=11))
        self.assertEqual(requests.sites[binding['label']]['methods'], {10, 11})
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            requests.observe(4, 'sha', 12, dict(binding, caller_method=12, dispatch=dict(binding['dispatch'], receiver_constraint=1)))
        with self.assertRaisesRegex(ValueError, 'caller identity'):
            requests.observe(5, 'sha', 10, binding)


if __name__ == '__main__': unittest.main()
