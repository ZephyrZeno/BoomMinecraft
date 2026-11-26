"""Keep missing runtime semantics explicit while grouping automatic work."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location('completion_planner', Path(__file__).resolve().parents[1] / 'scripts/plan-translation-completion.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def declaration(id_=7, loader='bootstrap', owner='java/lang/Class', code=None, access=0x101):
    return dict(id=id_, class_id=3, symbol=dict(loader=loader, owner=owner, name='query', descriptor='()Z'),
                class_sha256='source', code_sha256=code, access=access)


class CompletionPlannerTests(unittest.TestCase):
    def test_verified_provider_removes_direct_and_dispatch_requests_without_rewriting_base(self):
        decl=declaration();gap=dict(kind='native_declaration',protocol='native:7',native_method=7,symbols=['boom_m7'],affected_methods=[1])
        target=dict(method=7,class_id=3,defining_loader='bootstrap',class_sha256='source',owner='java/lang/Class',name='query',descriptor='()Z',access=0x101,java_assembly_emitted=False,native_binding_provided=False)
        tasks,actions=M.build_tasks([gap],[target],{7:decl},provided_native_ids={7})
        self.assertEqual((tasks,actions),([],[]));self.assertFalse(target['native_binding_provided'])

    def test_provider_does_not_hide_a_different_contract_or_Java_body(self):
        decl=declaration();gap=dict(kind='native_declaration',protocol='native:7',native_method=7,symbols=['different_contract'],affected_methods=[])
        with self.assertRaisesRegex(ValueError,'different source contract'):M.build_tasks([gap],[],{7:decl},provided_native_ids={7})
        gap['symbols']=['boom_m7'];decl['code_sha256']='Java'
        with self.assertRaisesRegex(ValueError,'Native gap differs'):M.build_tasks([gap],[],{7:decl},provided_native_ids={7})

    def test_direct_and_virtual_native_dependency_share_one_real_task(self):
        decl = declaration()
        gaps = [dict(kind='native_declaration', protocol='native:7', native_method=7,
                     symbols=['boom_m7'], affected_methods=[1, 2])]
        target = dict(method=7, class_id=3, defining_loader='bootstrap', class_sha256='source',
                      owner='java/lang/Class', name='query', descriptor='()Z', access=0x101,
                      java_assembly_emitted=False, native_binding_provided=False)
        tasks, _ = M.build_tasks(gaps, [target], {7: decl})
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]['symbols'], ['boom_m7'])
        self.assertEqual(tasks[0]['origins'], ['direct_contract', 'unprovided_dispatch_target'])
        self.assertEqual(tasks[0]['status'], 'requires_semantic_implementation')
        target['native_binding_provided'] = True
        self.assertEqual(M.build_tasks([], [target], {})[0], [])

    def test_loader_and_java_code_remain_distinct_from_native_implementation(self):
        a = declaration()
        b = declaration(8, loader='application')
        c = declaration(9, code='java-code', access=1)
        self.assertNotEqual(M.family('method', '', a), M.family('method', '', b))
        self.assertEqual(M.family('method', '', c)[1], 'source_or_backend_rule')
        self.assertEqual(M.family('method', '', a)[1], 'assembly_runtime_rule')

    def test_native_gap_cannot_claim_a_java_body(self):
        gap = dict(kind='native_declaration', protocol='native:7', native_method=7, symbols=['boom_m7'], affected_methods=[])
        with self.assertRaisesRegex(ValueError, 'Native gap'):
            M.build_tasks([gap], [], {7: declaration(code='Code')})

    def test_entry_priority_preserves_whole_input_requests_and_source_declarations(self):
        gaps = [dict(kind='invokedynamic', protocol='example/Bootstrap.link()V', native_method=None,
                     symbols=['a', 'b'], affected_methods=[1]),
                dict(kind='native_declaration', protocol='native:7', native_method=7,
                     symbols=['boom_m7'], affected_methods=[2])]
        frontier = dict(frontiers=[dict(kind='method', symbol='boom_m7', reason='missing', binding=None)])
        tasks, _ = M.build_tasks(gaps, [], {7: declaration()}, frontier)
        self.assertEqual(tasks[0]['entry_frontier_symbols'], ['boom_m7'])
        self.assertEqual({s for t in tasks for s in t['symbols']}, {'a', 'b', 'boom_m7'})
        self.assertEqual(tasks[1]['action'], 'bootstrap_lowering_rule')

    def test_direct_only_available_dispatch_is_an_expand_action(self):
        frontier = dict(frontiers=[dict(kind='virtual_dispatch', symbol='available', reason='unexpanded')])
        tasks, actions = M.build_tasks([], [], {}, frontier, {'available'})
        self.assertEqual(tasks, [])
        self.assertEqual(actions[0]['action'], 'expand_existing_static_dispatch')
        self.assertEqual(M.build_tasks([], [], {}, frontier)[0][0]['status'], 'requires_semantic_implementation')

    def test_batch_identity_prevents_old_or_other_side_frontier_reuse(self):
        summary = dict(input_fingerprint='inputs', ir_identity='IR')
        frontier = dict(source_input_fingerprint='inputs', batch_ir_identity='IR',
                        source_classes_sha256='classes', source_batch_summary_sha256='batch',
                        game_started=False, System_boot_phases_completed=False)
        M.validate_frontier(frontier, summary, 'batch', 'classes')
        for key in ('source_input_fingerprint', 'batch_ir_identity', 'source_classes_sha256', 'source_batch_summary_sha256'):
            changed = copy.deepcopy(frontier)
            changed[key] = 'different'
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'identity differs'):
                M.validate_frontier(changed, summary, 'batch', 'classes')

    def test_progress_compares_request_identities_and_rejects_scope_changes(self):
        previous = dict(input_fingerprint='inputs', ir_identity='IR', entry_scope='direct', requested_roots=[],
                        compiler_sha256='old', tasks=[dict(symbols=['old', 'same'])])
        current = dict(previous, tasks=[dict(symbols=['new', 'same'])])
        delta = M.compare(previous, current)
        self.assertEqual((delta['removed_requests'], delta['added_requests']), (['old'], ['new']))
        self.assertFalse(delta['same_missing_requests'])
        current['entry_scope'] = 'expanded'
        with self.assertRaisesRegex(ValueError, 'different inputs or scan'):
            M.compare(previous, current)

    def test_conflicting_symbol_ownership_is_rejected(self):
        def gap(protocol):
            return dict(kind='invokedynamic', protocol=protocol, native_method=None, symbols=['a'], affected_methods=[])
        with self.assertRaisesRegex(ValueError, 'Conflicting completion'):
            M.build_tasks([gap('a/Bootstrap.link()V'), gap('b/Bootstrap.link()V')], [], {})

    def test_missing_or_changed_artifact_cannot_publish_a_worklist(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'index.zip'
            path.write_bytes(b'original')
            record = dict(path=str(path), digest=dict(size=8, sha256=M.digest(path)))
            M.artifact(record)
            path.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'artifact changed'):
                M.artifact(record)


if __name__ == '__main__':
    unittest.main()
