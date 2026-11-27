"""A compiled Java method is not an invocation capability until selected."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('method_invoke_source_tests',ROOT/'scripts/method-invoke-source.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)


class MethodInvocationSelectionTests(unittest.TestCase):
    def setUp(self):
        self.row=dict(owner=10,slot=7,method=91,source_sha256='original-class',code_sha256='original-code',
            available=True,caller_sensitive=False,assembly_emitted=True,frame_flags=0)
        self.meta=dict(records=[self.row]);self.selected={'91':dict(class_id=10,source_sha256='original-class',code_sha256='original-code')}

    def test_only_explicit_current_selection_grants_real_entry(self):
        text,imports,sites=C.selected_sites(self.meta,[10],self.selected)
        self.assertIn('QWORD OFFSET boom_class10,OFFSET boom_m91,0,0',text)
        self.assertEqual(imports,{'boom_class10','boom_m91'});self.assertTrue(sites[0]['ready'])

    def test_compiled_but_unselected_target_stays_a_real_diagnostic(self):
        text,imports,sites=C.selected_sites(self.meta,[10],{})
        self.assertIn('QWORD OFFSET boom_class10,0,OFFSET boom_m91,0',text)
        self.assertFalse(sites[0]['ready']);self.assertEqual(sites[0]['reason'],'Java_Code_not_selected')
        self.assertEqual(sites[0]['callback'],'boom_m91')

    def test_class_not_selected_uses_its_original_initializer_stop(self):
        text,imports,sites=C.selected_sites(self.meta,[],self.selected)
        self.assertIn('QWORD 0,0,OFFSET boom_batch_initialize_10,0',text)
        self.assertEqual(imports,{'boom_batch_initialize_10'});self.assertFalse(sites[0]['ready'])

    def test_caller_sensitive_target_is_an_explicit_unsupported_slice(self):
        self.row.update(available=False,caller_sensitive=True)
        text,imports,sites=C.selected_sites(self.meta,[10],self.selected)
        self.assertIn('QWORD 0,0,0,0',text);self.assertEqual(imports,set())
        self.assertEqual(sites[0]['reason'],'caller_sensitive_unsupported')

    def test_changed_original_class_or_Code_is_rejected(self):
        for key in ('class_id','source_sha256','code_sha256'):
            data=deepcopy(self.selected);data['91'][key]='different'
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'Selected original method Code differs'):
                C.selected_sites(self.meta,[10],data)

    def test_nonemitted_body_cannot_be_marked_selected(self):
        self.row['assembly_emitted']=False
        with self.assertRaisesRegex(ValueError,'no available compiled source body'):
            C.selected_sites(self.meta,[10],self.selected)

    def test_selection_does_not_modify_immutable_source_records(self):
        before=deepcopy(self.meta);C.selected_sites(self.meta,[10],{})
        self.assertEqual(self.meta,before)


class MethodInvocationCandidateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('method_invoke_candidate_contract_tests',ROOT/'scripts/method-invoke-candidate.py')
        cls.B=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.B)

    def source_manifest(self):
        return dict(schema=1,family='source-method-invoke-static-reference-candidate',metadata=dict(input_state={}),
            registered=False,linked=False,executed=False,game_started=False,
            kernel=self.B.S.artifact(self.B.KERNEL),model=self.B.S.artifact(ROOT/'scripts/method-invoke-source.py'),
            tool=self.B.S.artifact(ROOT/'scripts/method-invoke-candidate.py'))

    def test_unregistered_source_manifest_cannot_claim_runtime_acceptance(self):
        for key in ('registered','linked','executed','game_started'):
            manifest=self.source_manifest();manifest[key]=True
            with self.subTest(key=key),patch.object(self.B.S,'read',return_value=manifest),patch.object(self.B,'contract') as contract:
                with self.assertRaisesRegex(ValueError,'source candidate scope differs'):
                    self.B.verify(Path('not-linked-candidate.json'))
                contract.assert_not_called()

    def test_manifest_native_symbols_must_equal_the_canonical_contract(self):
        for exports,imports in [(['boom_mUnexpected'],['boom_heap_contains']),
                (['boom_mOriginal','boom_mOriginal'],['boom_heap_contains']),(['boom_mOriginal'],[])]:
            manifest=self.source_manifest();manifest.update(exports=exports,imports=imports)
            with (self.subTest(exports=exports,imports=imports),
                    patch.object(self.B.S,'read',return_value=manifest),
                    patch.object(self.B.S,'checked',return_value=Path('unit-source-state')),
                    patch.object(self.B,'contract',return_value=manifest['metadata']),
                    patch.object(self.B,'assembly',return_value=('',{'boom_mOriginal'},{'boom_heap_contains'}))):
                with self.assertRaisesRegex(ValueError,'source symbols differ'):
                    self.B.verify(Path('not-linked-candidate.json'))


if __name__=='__main__':unittest.main()
