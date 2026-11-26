"""Strict count/namespace boundaries for focused accepted/pending source inputs."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('focused_state_boundaries',ROOT/'scripts/formal-provider-selection.py')
F=importlib.util.module_from_spec(spec);spec.loader.exec_module(F)


class FocusedStateBoundaries(unittest.TestCase):
    def setUp(self):
        base=ROOT/'.boom/focused-state-boundaries';base.mkdir(exist_ok=True)
        self.temporary=tempfile.TemporaryDirectory(dir=base);self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.namespace={'boundary_fixture':'source'}
        self.tool_patch=patch.object(F.S,'tools_identity',return_value=self.namespace);self.tool_patch.start();self.addCleanup(self.tool_patch.stop)

    def write(self,path,value):
        path.write_text(json.dumps(value),encoding='utf-8');return path

    def fixture(self,count=31,accepted=False):
        paths=[];records=[]
        for index in range(count):
            directory=self.root/str(index);directory.mkdir()
            manifest=self.write(directory/'provider.json',dict(family='fixture-'+str(index),tool_sources=self.namespace))
            proof=self.write(directory/'verification.json',dict(verified=True,provider_manifest_sha256=F.S.digest(manifest)['sha256']))
            paths.append(str(manifest));records.append(dict(family='fixture-'+str(index),manifest=F.S.artifact(manifest),verification=F.S.artifact(proof)))
        providers=self.write(self.root/'providers.json',paths)
        state=dict(status='accepted' if accepted else 'pending_runtime_acceptance',current_source_provider_verification_complete=True,
            runtime_acceptance_complete=accepted,accepted_provider_set_published=accepted,provider_count=count,
            batch=str(self.root/'batch'),plan=str(self.root/'plan'),runtime=str(self.root/'runtime'),providers=str(providers),
            providers_verified=records,tool_sources=self.namespace)
        return self.write(self.root/'state.json',state),state,paths

    def update_provider(self,state,index,*,manifest=None,proof=None):
        record=state['providers_verified'][index]
        m=Path(record['manifest']['path']);p=m.with_name('verification.json')
        if manifest is not None:self.write(m,manifest)
        current=F.S.read(p) if proof is None else proof
        if manifest is not None:current['provider_manifest_sha256']=F.S.digest(m)['sha256']
        self.write(p,current);record['manifest']=F.S.artifact(m);record['verification']=F.S.artifact(p)

    def test_pending31_and_legacy_accepted26_keep_distinct_scope(self):
        path,state,paths=self.fixture();actual,_,selected=F.state_inputs(path)
        self.assertEqual(len(selected),31);self.assertIs(actual['runtime_acceptance_complete'],False)
        # Parse an independent accepted26 state with the same current namespace.
        other=self.root/'accepted26';other.mkdir();self.root=other
        path,state,paths=self.fixture(26,True);actual,_,selected=F.state_inputs(path)
        self.assertEqual(len(F.provider_paths(paths)),26);self.assertEqual(len(selected),26)
        self.assertEqual(actual['status'],'accepted')

    def test_count_boolean_missing_or_wrong_length_is_rejected(self):
        path,state,_=self.fixture()
        for value in (True,0,26,32):
            changed=deepcopy(state);changed['provider_count']=value;self.write(path,changed)
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'exact sealed provider count'):F.state_inputs(path)

    def test_duplicate_manifest_is_rejected(self):
        path,state,paths=self.fixture();paths[-1]=paths[0];self.write(Path(state['providers']),paths)
        with self.assertRaisesRegex(ValueError,'without duplicates'):F.state_inputs(path)

    def test_receipt_count_and_original_order_are_fixed(self):
        path,state,_=self.fixture();changed=deepcopy(state);changed['providers_verified'].pop();self.write(path,changed)
        with self.assertRaisesRegex(ValueError,'receipt count'):F.state_inputs(path)
        state['providers_verified'].reverse();self.write(path,state)
        with self.assertRaisesRegex(ValueError,'order or sealed'):F.state_inputs(path)

    def test_resealed_duplicate_family_is_rejected(self):
        path,state,_=self.fixture();record=state['providers_verified'][1]
        m=F.S.read(record['manifest']['path']);m['family']='fixture-0';record['family']='fixture-0'
        self.update_provider(state,1,manifest=m);self.write(path,state)
        with self.assertRaisesRegex(ValueError,'families are duplicated'):F.state_inputs(path)

    def test_current_state_and_manifest_namespace_are_both_required(self):
        path,state,_=self.fixture();changed=deepcopy(state);changed['tool_sources']={'historical':'old'};self.write(path,changed)
        with self.assertRaisesRegex(ValueError,'historical tool namespace'):F.state_inputs(path)
        m=F.S.read(state['providers_verified'][0]['manifest']['path']);m['tool_sources']={'historical':'old'}
        self.update_provider(state,0,manifest=m);self.write(path,state)
        with self.assertRaisesRegex(ValueError,'current identity'):F.state_inputs(path)

    def test_resealed_false_or_unbound_receipt_is_rejected(self):
        path,state,_=self.fixture();proof=F.S.read(state['providers_verified'][0]['verification']['path'])
        for changes in ({'verified':False},{'provider_manifest_sha256':'0'*64}):
            changed=dict(proof,**changes);self.update_provider(state,0,proof=changed);self.write(path,state)
            with self.subTest(changes=changes),self.assertRaisesRegex(ValueError,'receipt binding'):F.state_inputs(path)

    def test_pending_cannot_become_accepted_through_flags(self):
        path,state,_=self.fixture()
        for changes in ({'runtime_acceptance_complete':True},{'accepted_provider_set_published':True},
                        {'current_source_provider_verification_complete':False},{'status':'accepted'}):
            self.write(path,dict(state,**changes))
            with self.subTest(changes=changes),self.assertRaises(ValueError):F.state_inputs(path)


if __name__=='__main__':unittest.main()
