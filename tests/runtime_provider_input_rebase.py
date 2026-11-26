"""Negative boundaries for the explicit pending31 same-input source rebase."""
import ast
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('provider_input_rebase_test', ROOT/'scripts/rebase-runtime-provider-inputs.py')
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


class ProviderInputRebaseBoundaries(unittest.TestCase):
    def test_tool_append_does_not_authorize_source_logic_changes(self):
        old = b"TOOL_FILES=('a','b')\ndef check(x):return x+1\n"
        new = b"TOOL_FILES=('a','b','c')\ndef check(x):return x+1\n"
        proof = R.same_source_model(old, new)
        self.assertEqual(proof['appended_tools'], ['c'])
        with self.assertRaisesRegex(ValueError, 'source logic changed'):
            R.same_source_model(old, new.replace(b'x+1', b'x+2'))

    def test_old_tool_order_and_membership_remain_fixed(self):
        old = b"TOOL_FILES=('a','b')\n"
        for current in (b"TOOL_FILES=('b','a','c')\n", b"TOOL_FILES=('a','other','c')\n", old):
            with self.subTest(current=current), self.assertRaisesRegex(ValueError, 'append-only'):
                R.same_source_model(old, current)

    def test_dynamic_or_ambiguous_tool_lists_are_rejected(self):
        old = b"TOOL_FILES=('a','b')\n"
        for current in (b"TOOL_FILES=('a','b','b')\n", b"TOOL_FILES=('a','b')\nTOOL_FILES=TOOL_FILES+('c',)\n",
                        b"TOOL_FILES=other=('a','b','c')\n", b"TOOL_FILES=['a','b','c']\n"):
            with self.subTest(current=current), self.assertRaises(ValueError):
                R.same_source_model(old, current)

    @staticmethod
    def summary():
        return dict(class_literals=dict(units=[dict(assembly={'path':'old.asm'}, object={'path':'old.obj'}, classes=3)],
                                        modules=[dict(id=0,name='java.base',loader=0),dict(id=64,name='jdk.jdwp.agent',loader=2)],
                                        type_layout={'abi':6,'root_count':110013}),
                    properties={'roots':109}, source_profile={'included_classes':[1,2]},
                    shards=[{'units':[{'assembly':{'path':'java.asm'},'object':{'path':'java.obj'},'code_sha256':'original'}]}])

    def test_only_JCLS_artifact_locations_may_change(self):
        before = self.summary()
        after = deepcopy(before)
        after['class_literals']['units'][0].update(assembly={'path':'new.asm'},object={'path':'new.obj'})
        R.same_summary(before, after)
        for section, key, replacement in [('properties','roots',110), ('source_profile','included_classes',[1,2,3])]:
            changed = deepcopy(after)
            changed[section][key] = replacement
            with self.subTest(section=section), self.assertRaisesRegex(ValueError, 'beyond JCLS artifact locations'):
                R.same_summary(before, changed)

    def test_old_module_slots_and_layout_cannot_move(self):
        before = self.summary()
        changed = deepcopy(before)
        changed['class_literals']['modules'].reverse()
        with self.assertRaises(ValueError):R.same_summary(before, changed)
        changed = deepcopy(before)
        changed['class_literals']['type_layout']['root_count'] += 1
        with self.assertRaises(ValueError):R.same_summary(before, changed)

    def test_retained_Java_Code_and_COFF_cannot_change(self):
        before = self.summary()
        for key, value in [('code_sha256','changed'), ('object',{'path':'other.obj'})]:
            changed = deepcopy(before)
            changed['shards'][0]['units'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):R.same_summary(before, changed)

    def test_full_receipt_preserves_every_coverage_and_execution_flag(self):
        before = dict(verified=True,frames={'verified':True},weak_GC_complete=False,game_started=False,
                      named_module_derivation={'path':'old'},bootstrap_unnamed_derivation={'slot':63})
        after = deepcopy(before)
        after['named_module_derivation'] = {'path':'new'}
        R.same_full_coverage(before, after)
        for key, value in [('verified',False), ('frames',{'verified':False}), ('weak_GC_complete',True),
                           ('game_started',True), ('bootstrap_unnamed_derivation',{'slot':64})]:
            changed = deepcopy(after)
            changed[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'coverage differs'):
                R.same_full_coverage(before, changed)
        del after['frames']
        with self.assertRaises(ValueError):R.same_full_coverage(before, after)

    def test_wrong_original_pending_checksum_fails_before_output(self):
        base = ROOT/'.boom/provider-input-rebase-tests'
        base.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as temporary:
            old = Path(temporary)/'pending.json'
            old.write_text('{}', encoding='utf-8')
            output = ROOT/'.boom/runtime-provider-rebases'/Path(temporary).name
            with self.assertRaisesRegex(ValueError, 'state checksum differs'):
                R.rebase(old, '0'*64, ROOT/'.boom/named-module-batches/nonexistent', '0'*64, old, output)
            self.assertFalse(output.exists())

    def test_rebase_does_not_invoke_an_assembler_or_change_parent_rules(self):
        # The producer delegates all current frame/provider models; no assembler,
        # process launcher, or extend-runtime-provider-set mutation is present.
        tree = ast.parse((ROOT/'scripts/rebase-runtime-provider-inputs.py').read_text(encoding='utf-8'))
        imports = {node.name for node in ast.walk(tree) if isinstance(node, ast.alias)}
        self.assertFalse({'subprocess','shutil'} & imports)
        calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertTrue({'refresh_frames','refresh_packs','verified_resolver','binary_equivalence'} <= calls)


if __name__ == '__main__':unittest.main()
