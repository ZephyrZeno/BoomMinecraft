"""A process-local graph cache never substitutes current input content checks."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]

def module(root=ROOT,file='provider-tool-manifest.py'):
    spec=importlib.util.spec_from_file_location('fresh_tool_graph_'+uuid4().hex,root/'scripts'/file)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

H=module()


class FreshImportGraphCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract=H.load(ROOT)
        cls.paths=set(cls.contract['tool_files'])|set(cls.contract['runtime_contract_sources'])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='fresh-audit-',dir=ROOT/'.boom');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.assertTrue(self.root.is_relative_to(ROOT/'.boom'))
        for name in self.paths:
            destination=self.root/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,destination)

    def fresh(self):return module(self.root)

    def test_fresh_helper_reuses_only_same_content_graph_and_keeps_tuple(self):
        first=self.fresh()
        with patch.object(first,'load',wraps=first.load) as audit:
            files=first.tool_files(self.root);self.assertEqual(audit.call_count,1)
        second=self.fresh()
        with patch.object(second,'load',side_effect=AssertionError('same graph was re-audited')):
            self.assertEqual(second.tool_files(self.root),files)
            contract,identity=second._audited_identity(self.root)
        self.assertIsInstance(contract['tool_files'],tuple)
        self.assertEqual(contract,H.load(self.root));self.assertEqual(len(identity),len(self.contract['tool_files']))

    def test_fresh_S_import_uses_the_same_cache_without_changing_S(self):
        before=self.fresh();before.tool_files(self.root)
        with patch.object(before,'load',side_effect=AssertionError('unexpected direct same-instance load')):
            source=module(self.root,'runtime-provider-source.py')
        self.assertEqual(source.TOOL_FILES,before.tool_files(self.root))
        self.assertEqual(source.tools_identity(),before.tools_identity(self.root))
        self.assertEqual((self.root/'scripts/runtime-provider-source.py').read_bytes(),(ROOT/'scripts/runtime-provider-source.py').read_bytes())

    def test_every_cache_hit_reads_and_hashes_the_complete_current_tool_order(self):
        self.fresh().tool_files(self.root);current=self.fresh()
        original_read=Path.read_bytes;reads=[]
        def record(path):
            reads.append(path.resolve());return original_read(path)
        with patch.object(Path,'read_bytes',record),patch.object(current,'_identity_bytes',wraps=current._identity_bytes) as identity:
            result=current.tools_identity(self.root)
        self.assertEqual(identity.call_count,1)
        self.assertEqual(tuple(identity.call_args.args[1]),self.contract['tool_files'])
        self.assertEqual(set(result),set(self.contract['tool_files']))
        self.assertTrue({(self.root/name).resolve() for name in self.contract['tool_files']}<=set(reads))

    def test_returned_contract_identity_and_snapshot_cannot_mutate_shared_bytes(self):
        first=self.fresh();contract,identity=first._audited_identity(self.root);contract['family_sources'].clear();identity.clear()
        second=self.fresh();actual,new_identity=second._audited_identity(self.root)
        self.assertEqual(actual,H.load(self.root));self.assertEqual(len(new_identity),len(self.contract['tool_files']))
        holder=second._process_graph_cache()
        self.assertTrue(all(isinstance(value,bytes) for value in holder.entries.values()))
        self.assertTrue(all(isinstance(key,tuple) and len(key)==3 and isinstance(key[2],tuple) for key in holder.entries))

    def test_same_size_same_mtime_source_change_forces_a_fresh_audit(self):
        self.fresh().tool_files(self.root);path=self.root/'scripts/file-input-source.py';before=path.stat();raw=path.read_bytes()
        changed=raw.replace(b'Eight',b'eight',1);self.assertNotEqual(raw,changed);self.assertEqual(len(raw),len(changed))
        path.write_bytes(changed);os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns));current=self.fresh()
        with patch.object(current,'load',wraps=current.load) as audit:identity=current.tools_identity(self.root)
        self.assertEqual(audit.call_count,1);self.assertEqual(identity['scripts/file-input-source.py'],H.sha256(changed))

    def test_same_size_same_mtime_manifest_change_cannot_hit_previous_graph(self):
        self.fresh().tool_files(self.root);path=self.root/H.MANIFEST;before=path.stat();raw=path.read_bytes()
        changed=raw.replace(b'"schema": 1',b'"schema": 2',1);self.assertEqual(len(raw),len(changed));path.write_bytes(changed)
        os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns));current=self.fresh()
        with patch.object(current,'load',wraps=current.load) as audit,self.assertRaisesRegex(ValueError,'Unsupported tool-manifest schema'):
            current.tool_files(self.root)
        self.assertEqual(audit.call_count,1)

    def test_new_undeclared_dependency_is_not_hidden_by_shared_cache(self):
        self.fresh().tool_files(self.root);path=self.root/'scripts/file-input-source.py'
        path.write_bytes(path.read_bytes()+b"\nS.module('undeclared','unlisted-model.py')\n")
        with self.assertRaisesRegex(ValueError,'not explicitly declared'):self.fresh().tools_identity(self.root)

    def test_runtime_paths_are_rechecked_even_on_cross_instance_hit(self):
        self.fresh().tool_files(self.root);current=self.fresh();runtime=self.contract['runtime_contract_sources']
        with patch.object(current,'source_path',wraps=current.source_path) as paths:
            current.tool_files(self.root)
        checked={call.args[1] for call in paths.call_args_list};self.assertTrue(set(runtime)<=checked)
        (self.root/runtime[0]).unlink()
        with self.assertRaisesRegex(ValueError,'Missing or escaped source file'):self.fresh().tool_files(self.root)

    def test_root_and_implementation_identity_are_independent_keys(self):
        first=self.fresh();first.tool_files(self.root)
        # Another root containing the exact same source bytes needs its own
        # path/escape audit; copying is not a source acceptance shortcut.
        with tempfile.TemporaryDirectory(prefix='another-audit-',dir=ROOT/'.boom') as directory:
            other=Path(directory)
            for name in self.paths:
                p=other/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(self.root/name,p)
            current=module(other)
            with patch.object(current,'load',wraps=current.load) as audit:current.tool_files(other)
            self.assertEqual(audit.call_count,1)
        helper=self.root/H.HELPER;helper.write_bytes(helper.read_bytes()+b'\n# independent helper implementation identity\n')
        with self.assertRaisesRegex(ValueError,'Loaded helper full source identity changed'):first.tool_files(self.root)
        current=self.fresh()
        with patch.object(current,'load',wraps=current.load) as audit:identity=current.tools_identity(self.root)
        self.assertEqual(audit.call_count,1);self.assertEqual(identity[H.HELPER],H.sha256(helper.read_bytes()))

    def test_explicit_load_and_runtime_snapshot_remain_fresh(self):
        current=self.fresh();current.tool_files(self.root)
        with patch.object(current,'validate_api_consumers',wraps=current.validate_api_consumers) as audit:
            current.load(self.root);current.load(self.root)
        self.assertEqual(audit.call_count,2)
        before=current.snapshot(self.root);path=self.root/self.contract['runtime_contract_sources'][0]
        path.write_bytes(path.read_bytes()+b'\n; fresh runtime source content\n');after=self.fresh().snapshot(self.root)
        self.assertEqual(before['tool_sources'],after['tool_sources'])
        self.assertNotEqual(before['separately_required_runtime_sources'],after['separately_required_runtime_sources'])
        self.assertFalse(after['provider_packs_revalidated']);self.assertFalse(after['named_batch_revalidated'])


if __name__=='__main__':unittest.main()
