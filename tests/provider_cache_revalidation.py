"""A copied native object is not accepted until the current source model passes."""
from contextlib import nullcontext
import importlib.util
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('provider_cache_acceptance_tests',ROOT/'scripts/revalidate-runtime-provider-cache.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


class ProviderCacheRevalidationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'.boom/runtime-providers');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)

    def test_copy_keeps_exact_original_bytes(self):
        source=self.root/'provider.obj';source.write_bytes(b'own object bytes');output=self.root/'out';output.mkdir()
        record=M.S.artifact(source);result=M.copy_record(record,output)
        self.assertEqual(result['digest'],record['digest']);self.assertEqual(Path(result['path']).read_bytes(),source.read_bytes())

    def base(self):
        return dict(input_fingerprint='a',ir_identity='b',runtime_layout_abi=1,context_bytes=32,
            source_frame_abi=3,class_pool_abi=1,source_transform_chain='original',base_compiler_sha256='old',
            **{k:dict(digest=dict(size=1,sha256='c')) for k in ('source_classes','source_methods','source_plan')})

    def test_same_source_new_compiler_is_only_a_reuse_precondition(self):
        old=self.base();new=copy.deepcopy(old);new['base_compiler_sha256']='new'
        self.assertEqual(M.compatible_base(old,new),new)

    def test_changed_class_bytes_cannot_rebind_a_cache(self):
        old=self.base();new=copy.deepcopy(old);new['source_classes']['digest']['sha256']='changed'
        with self.assertRaisesRegex(ValueError,'original source changed'):M.compatible_base(old,new)

    def test_changed_runtime_abi_cannot_rebind_a_cache(self):
        old=self.base();new=copy.deepcopy(old);new['context_bytes']=16
        with self.assertRaisesRegex(ValueError,'source/ABI changed'):M.compatible_base(old,new)

    def test_changed_original_cache_is_rejected(self):
        source=self.root/'provider.obj';source.write_bytes(b'original');record=M.S.artifact(source);source.write_bytes(b'changed!')
        output=self.root/'out';output.mkdir()
        with self.assertRaisesRegex(ValueError,'changed'):M.copy_record(record,output)

    def test_prior_verified_flag_cannot_publish_current_success(self):
        previous=self.root/'old';previous.mkdir()
        asm=previous/'provider.asm';asm.write_text('not a current source model')
        obj=previous/'provider.obj';obj.write_bytes(b'not a current COFF contract')
        provider=previous/'provider.json';provider.write_text(json.dumps(dict(family='example',assembly=M.S.artifact(asm),object=M.S.artifact(obj),tool_sources={},elapsed_ms=1)))
        (previous/'verification.json').write_text(json.dumps(dict(verified=True,provider_manifest_sha256=M.S.digest(provider)['sha256'])))
        frames=self.root/'frames';frames.mkdir();frame=frames/'overlay.json';frame.write_text('{}');(frames/'verification.json').write_text('{}')
        verifier=SimpleNamespace(S=SimpleNamespace(base_scope=lambda *a:nullcontext()))
        def reject(*args):raise ValueError('current source mismatch')
        verifier.verify=reject;output=self.root/'new'
        with patch.object(M.S,'module',return_value=verifier):
            with self.assertRaisesRegex(ValueError,'current source mismatch'):M.refresh_packs([provider],self.root,self.root,frame,output)
        self.assertFalse((output/'example/verification.json').exists());self.assertFalse((output/'accepted-caches.json').exists())


if __name__=='__main__':unittest.main()
