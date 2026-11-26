"""Batch replacement retains the original payload and never grants execution."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('provider_batch_equivalence',ROOT/'scripts/extend-runtime-provider-set.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)
Q=M.module('rebase-runtime-provider-inputs')


class EquivalentNamedBatchBoundaries(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'.boom');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.old=self.root/'old';self.new=self.root/'new'
        self.old.mkdir();self.new.mkdir();self.plan=self.root/'plan'
        self.binary=dict(BSS_added_bytes=0,indexed_symbol_contract=dict(rdata_symbol_shift=0,BSS_symbol_shift=0))
        for directory in (self.old,self.new):
            for name in ('unit.asm','unit.obj'):(directory/name).write_bytes(b'isolated boundary fixture, not compiled code')
            self.write(directory/'summary.json',dict(class_literals=dict(units=[dict(
                assembly=M.S.artifact(directory/'unit.asm'),object=M.S.artifact(directory/'unit.obj'))],
                modules=[dict(id=0,name='java.base',loader=0)],type_capacity=4),
                source_profile=dict(classes=[1,2]),shards=[dict(code_sha256='original',object='retained')]))
            self.write(directory/'named-module-derivation.json',dict(parent_inputs={'original':'pinned'},
                parent_derivation={'original':'pinned'},requested_modules=['jdk.fixture'],source_graph={'inputs':{'graph':'original'}},
                appended=[dict(id=1,name='jdk.fixture',loader=2)],declaration_changes=['original'],binary_equivalence={'original':True},
                tools={'helper':'old' if directory==self.old else 'new'}))
            derived=M.S.read(directory/'named-module-derivation.json')
            scope=dict(summary=M.S.artifact(directory/'summary.json'),derivation=M.S.artifact(directory/'named-module-derivation.json'),
                parent=derived['parent_inputs'],source_graph=derived['source_graph']['inputs'])
            self.write(directory/'verification.json',dict(verified=True,frames={'verified':True},game_started=False,
                named_module_derivation=scope))
        self.N=SimpleNamespace(PROOF='named-module-derivation.json',artifact=M.S.artifact,checked=M.S.checked,
            verified_resolver=Mock(return_value=(None,dict(scope='fresh-current-full-proof'))),
            binary_equivalence=Mock(return_value=self.binary))
        self.loader=patch.object(M,'module',side_effect=lambda name: self.N if name=='refresh-named-module-batch' else Q)
        self.loader.start();self.addCleanup(self.loader.stop)

    @staticmethod
    def write(path,value):path.write_text(json.dumps(value),encoding='utf-8')

    def run_contract(self,sha=None):
        return M.equivalent_named_batch(self.old,self.new,self.plan,
            sha or M.S.digest(self.new/'verification.json')['sha256'])

    def change(self,name,mutate,directory=None):
        path=(directory or self.new)/name;value=M.S.read(path);mutate(value);self.write(path,value)

    def test_full_current_resolver_and_machine_equivalence_are_required(self):
        proof=self.run_contract()
        self.N.verified_resolver.assert_called_once();self.N.binary_equivalence.assert_called_once()
        self.assertFalse(proof['runtime_acceptance_proven'])
        self.assertTrue(proof['current_provider_models_must_reverify'])

    def test_explicit_new_full_checksum_precedes_resolver(self):
        with self.assertRaisesRegex(ValueError,'checksum differs'):self.run_contract('0'*64)
        self.N.verified_resolver.assert_not_called()

    def test_current_strict_resolver_failure_is_never_bypassed(self):
        self.N.verified_resolver.side_effect=ValueError('current full proof rejected')
        with self.assertRaisesRegex(ValueError,'current full proof rejected'):self.run_contract()

    def test_original_Java_units_and_source_selection_cannot_change(self):
        original=M.S.read(self.new/'summary.json')
        for section,key,value in (('source_profile','classes',[1,2,3]),):
            self.write(self.new/'summary.json',deepcopy(original))
            self.change('summary.json',lambda row:row[section].update({key:value}))
            with self.assertRaisesRegex(ValueError,'beyond JCLS'):self.run_contract()
        self.write(self.new/'summary.json',original)
        self.change('summary.json',lambda row:row['shards'][0].update(code_sha256='changed'))
        with self.assertRaisesRegex(ValueError,'beyond JCLS'):self.run_contract()

    def test_module_capacity_and_full_coverage_flags_cannot_change(self):
        original=M.S.read(self.new/'summary.json')
        self.change('summary.json',lambda row:row['class_literals'].update(type_capacity=5))
        with self.assertRaises(ValueError):self.run_contract()
        self.write(self.new/'summary.json',original)
        self.change('verification.json',lambda row:row.update(game_started=True))
        with self.assertRaisesRegex(ValueError,'coverage differs'):self.run_contract()

    def test_accepted_derivation_and_original_module_graph_remain_bound(self):
        original=M.S.read(self.old/'verification.json')
        self.change('verification.json',lambda row:row['named_module_derivation']['derivation']['digest'].update(sha256='0'*64),self.old)
        with self.assertRaisesRegex(ValueError,'original derivation'):self.run_contract()
        self.write(self.old/'verification.json',original)
        self.change('named-module-derivation.json',lambda row:row['source_graph']['inputs'].update(graph='different'))
        with self.assertRaisesRegex(ValueError,'source graph or append'):self.run_contract()

    def test_JCLS_assembly_and_symbol_positions_cannot_change(self):
        changed=self.new/'unit.asm';changed.write_bytes(b'changed assembly')
        self.change('summary.json',lambda row:row['class_literals']['units'][0].update(assembly=M.S.artifact(changed)))
        with self.assertRaisesRegex(ValueError,'assembly bytes changed'):self.run_contract()
        changed.write_bytes((self.old/'unit.asm').read_bytes())
        self.change('summary.json',lambda row:row['class_literals']['units'][0].update(assembly=M.S.artifact(changed)))
        for key in ('rdata_symbol_shift','BSS_symbol_shift'):
            self.binary['indexed_symbol_contract'][key]=8
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'COFF data or symbol layout'):self.run_contract()
            self.binary['indexed_symbol_contract'][key]=0
        self.binary['BSS_added_bytes']=8
        with self.assertRaisesRegex(ValueError,'COFF data or symbol layout'):self.run_contract()


if __name__=='__main__':unittest.main()
