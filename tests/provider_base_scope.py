"""Fresh in-process base reuse must reject disk or in-memory source changes."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('provider_base_scope_tests',ROOT/'scripts/runtime-provider-source.py')
S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)


class ProviderBaseScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'.boom');self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name);self.batch=self.directory/'batch';self.plan=self.directory/'plan';self.batch.mkdir();self.plan.mkdir()
        self.identity={}
        for name in ('batch_summary','base_verification','source_plan','source_classes','source_methods'):
            path=self.directory/(name+'.json');path.write_text(name);self.identity[name]=S.artifact(path)
        self.snapshot=(self.identity,dict(schema=23),[dict(id=0,name='Original')])

    def test_only_reuses_fresh_base_inside_the_scope(self):
        with patch.object(S,'_fresh_base',return_value=self.snapshot) as fresh:
            with S.base_scope(self.batch,self.plan):
                self.assertIs(S.base(self.batch,self.plan),self.snapshot)
                self.assertIs(S.base(self.batch,self.plan),self.snapshot)
                self.assertEqual(fresh.call_count,1)
            self.assertIsNone(S._BASE_SCOPE.get());S.base(self.batch,self.plan);self.assertEqual(fresh.call_count,2)

    def test_rejects_changed_source_artifact_before_success(self):
        with patch.object(S,'_fresh_base',return_value=self.snapshot):
            with self.assertRaisesRegex(ValueError,'Shared provider base changed'):
                with S.base_scope(self.batch,self.plan):Path(self.identity['source_methods']['path']).write_text('modified')
        self.assertIsNone(S._BASE_SCOPE.get())

    def test_rejects_mutation_of_the_shared_python_snapshot(self):
        with patch.object(S,'_fresh_base',return_value=self.snapshot):
            with self.assertRaisesRegex(ValueError,'mutated'):
                with S.base_scope(self.batch,self.plan):self.snapshot[2][0]['name']='Changed'
        self.assertIsNone(S._BASE_SCOPE.get())

    def test_rejects_another_batch_without_leaking_context(self):
        with patch.object(S,'_fresh_base',return_value=self.snapshot):
            with self.assertRaisesRegex(ValueError,'another batch'):
                with S.base_scope(self.batch,self.plan):S.base(self.batch/'other',self.plan)
        self.assertIsNone(S._BASE_SCOPE.get())

    def test_rejects_nested_scopes(self):
        with patch.object(S,'_fresh_base',return_value=self.snapshot):
            with self.assertRaisesRegex(ValueError,'Nested'):
                with S.base_scope(self.batch,self.plan):
                    with S.base_scope(self.batch,self.plan):pass
        self.assertIsNone(S._BASE_SCOPE.get())


if __name__=='__main__':unittest.main()
