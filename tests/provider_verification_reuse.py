"""A process-local handoff must reject changed package, base or tool bytes."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


def load(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).resolve().parents[1]/'scripts'/file)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


M=load('provider_handoff_tests','provider-verification-reuse.py')
S=load('provider_handoff_test_identity','runtime-provider-source.py')


class ProviderHandoffTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(prefix='provider-handoff-test-',dir=S.ART)
        self.addCleanup(self.directory.cleanup);self.root=Path(self.directory.name)
        self.batch=self.root/'batch';self.plan=self.root/'plan';self.batch.mkdir();self.plan.mkdir()
        base=dict(batch=str(self.batch),plan=str(self.plan))
        for key in ('batch_summary','base_verification','source_plan','source_classes','source_methods'):
            p=self.root/(key+'.json');p.write_text(key);base[key]=S.artifact(p)
        self.manifest=dict(base=base,tool_sources=S.tools_identity());self.path=self.root/'provider.json'
        self.path.write_text(json.dumps(self.manifest));proof=self.root/'verification.json';proof.write_text('{"verified":true}')
        self.packs=[dict(manifest=self.manifest,reference=S.artifact(self.path),verification=S.artifact(proof))]
        self.verifier=SimpleNamespace(S=S)

    def use(self,packs=None,paths=None,batch=None,plan=None):
        return M.reuse(self.verifier,batch or self.batch,plan or self.plan,
                       [self.path] if paths is None else paths,self.packs if packs is None else packs)

    def test_same_call_chain_reuses_the_verified_objects(self):
        self.assertIs(self.use(),self.packs)

    def test_changed_manifest_receipt_or_base_file_is_rejected(self):
        paths=[self.path,Path(self.packs[0]['verification']['path']),Path(self.manifest['base']['source_classes']['path'])]
        for path in paths:
            before=path.read_bytes();path.write_bytes(before+b' ')
            try:
                with self.subTest(path=path.name),self.assertRaisesRegex(ValueError,'changed'):self.use()
            finally:path.write_bytes(before)

    def test_wrong_identity_set_or_mutated_cached_manifest_is_rejected(self):
        for kwargs in [dict(paths=[]),dict(batch=self.root/'other-batch'),dict(plan=self.root/'other-plan')]:
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):self.use(**kwargs)
        packs=copy.deepcopy(self.packs);packs[0]['manifest']['unexpected']=True
        with self.assertRaisesRegex(ValueError,'manifest bytes'):self.use(packs=packs)

    def test_changed_provider_tool_identity_is_rejected(self):
        with patch.object(S,'tools_identity',return_value={'changed':'f'*64}):
            with self.assertRaisesRegex(ValueError,'tool identity'):self.use()


if __name__=='__main__':unittest.main()
