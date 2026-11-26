"""Standalone tool graph must preserve order and reject hidden source changes."""
import ast
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('provider_tool_manifest_tests',ROOT/'scripts/provider-tool-manifest.py')
H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)


class ProviderToolManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'.boom');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.assertTrue(self.root.is_relative_to(ROOT/'.boom'))
        self.data=H.read(ROOT/H.MANIFEST);contract=H.load()
        self.paths=set(self.data['tool_order'])|set(contract['runtime_contract_sources'])
        for name in self.paths:
            target=self.root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)

    def write(self):
        (self.root/H.MANIFEST).write_text(json.dumps(self.data,indent=2)+'\n',encoding='utf-8')

    def refresh(self,name):
        self.data['dependency_audits'][name]=H.source_audit(self.root,name,self.data['api_scopes'].get(name),self.data['data_bound_imports'].get(name))
        self.write()

    def invalid(self,message=None):
        self.write()
        with self.assertRaisesRegex(ValueError,message or '.'):
            H.load(self.root)

    def test_complete_current_prefix_and_control_identity(self):
        current=H.load(self.root)
        self.assertEqual(H.path_digest(current['tool_files'][:105]),H.LEGACY_PATH_SHA256)
        self.assertEqual(current['tool_files'][105:107],(H.HELPER,H.MANIFEST))
        identity=H.tools_identity(self.root)
        self.assertEqual(len(identity),len(self.data['tool_order']))
        for name in (H.HELPER,H.MANIFEST,H.REGISTRY):self.assertEqual(identity[name],H.sha256((self.root/name).read_bytes()))

    def test_identity_round_trip_is_fresh(self):
        proof=json.loads(json.dumps(H.snapshot(self.root)))
        self.assertEqual(H.verify_snapshot(proof,self.root),proof)

    def test_duplicate_json_key_rejected(self):
        (self.root/H.MANIFEST).write_text('{"schema":1,"schema":1}')
        with self.assertRaisesRegex(ValueError,'Duplicate JSON key'):H.load(self.root)

    def test_prefix_reorder_cannot_be_redeclared(self):
        self.data['tool_order'][0],self.data['tool_order'][1]=self.data['tool_order'][1],self.data['tool_order'][0]
        self.invalid('105-tool order')
        self.data['legacy_prefix']['sha256']=H.path_digest(self.data['tool_order'][:105])
        self.invalid('Immutable legacy')

    def test_duplicate_tool_rejected(self):
        self.data['tool_order'].append(self.data['tool_order'][0]);self.invalid('Duplicate')

    def test_case_alias_rejected(self):
        self.data['tool_order'].append(self.data['tool_order'][0].upper());self.invalid('Duplicate')

    def test_traversal_absolute_backslash_and_drive_rejected(self):
        for name in ('scripts/../outside.py','C:/outside.py','/outside.py','scripts\\outside.py','scripts//outside.py'):
            with self.subTest(path=name),self.assertRaises(ValueError):H.source_path(self.root,name)

    def test_missing_helper_and_manifest_identity_rejected(self):
        for name in (H.HELPER,H.MANIFEST):
            with self.subTest(path=name):
                before=deepcopy(self.data);self.data['tool_order'].remove(name);self.invalid();self.data=before

    def test_unknown_and_missing_family_rejected(self):
        before=deepcopy(self.data);self.data['families']['unregistered']=next(iter(self.data['families'].values()))
        self.invalid('Unknown or missing registry family');self.data=before
        self.data['families'].pop(next(iter(self.data['families'])));self.invalid('Unknown or missing registry family')

    def test_registry_kernel_must_match_actual_family(self):
        family=next(iter(self.data['families']));self.data['families'][family]['kernel']='native/providers/identity.asm.inc'
        self.invalid('Registry kernel')

    def test_family_model_cannot_be_omitted_or_swapped(self):
        family=next(name for name,row in self.data['families'].items() if row['model'])
        row=self.data['families'][family];row['owned_files'].remove(row['model']);self.invalid('must own')
        row['owned_files'].append(row['model']);row['model']='scripts/file-bootstrap-source.py';self.invalid('binding differs')

    def test_loader_boundary_is_not_assumed_bootstrap(self):
        family=next(iter(self.data['families']));self.data['families'][family]['source_scope']['loader']='mod:unbound'
        self.invalid('loader boundary')

    def test_consistent_mod_loader_boundary_is_data_only(self):
        family=next(iter(self.data['families']));registry=H.read(self.root/H.REGISTRY)
        registry['families'][family].update(loader='mod:isolated-namespace',source_id='fixture:tool-identity')
        (self.root/H.REGISTRY).write_text(json.dumps(registry),encoding='utf-8')
        self.data['families'][family]['source_scope'].update(loader='mod:isolated-namespace',source_id='fixture:tool-identity')
        self.write();self.assertEqual(H.load(self.root)['family_sources'][family]['source_scope']['loader'],'mod:isolated-namespace')
        # This accepts a path/identity namespace only; original Java source and
        # native bindings remain the responsibility of the ordinary pack proof.

    def test_missing_dependency_audit_rejected(self):
        self.data['dependency_audits'].pop(next(iter(self.data['dependency_audits'])));self.invalid('Missing or extra source dependency audit')

    def test_implicit_python_module_dependency_rejected(self):
        path=self.root/'scripts/file-input-source.py'
        path.write_text(path.read_text()+"\nS.module('new_unlisted', 'unlisted-model.py')\n")
        with self.assertRaisesRegex(ValueError,'not explicitly declared'):H.load(self.root)
        self.refresh('scripts/file-input-source.py')
        with self.assertRaisesRegex(ValueError,'Implicit undeclared source'):H.load(self.root)

    def test_bare_local_import_must_be_declared(self):
        extra=self.root/'scripts/unlisted_local.py';extra.write_text('value=1\n')
        path=self.root/'scripts/file-input-source.py';path.write_text(path.read_text()+'\nimport unlisted_local\n')
        with self.assertRaisesRegex(ValueError,'not explicitly declared'):H.load(self.root)
        self.refresh('scripts/file-input-source.py')
        with self.assertRaisesRegex(ValueError,'Implicit undeclared source'):H.load(self.root)

    def test_unknown_dynamic_source_load_rejected_after_audit_refresh(self):
        path=self.root/'scripts/file-input-source.py';path.write_text(path.read_text()+"\nS.module('unknown', dynamic_filename)\n")
        self.refresh('scripts/file-input-source.py')
        with self.assertRaisesRegex(ValueError,'undeclared dynamic source load'):H.load(self.root)

    def test_unbound_importlib_data_path_rejected(self):
        self.data['data_bound_imports'].clear();self.invalid('Unknown dynamic importlib')

    def test_unlisted_embedded_asm_cannot_hide_as_runtime(self):
        path=self.root/'scripts/file-input-source.py';path.write_text(path.read_text()+"\nEMBEDDED='native/providers/unlisted.asm.inc'\n")
        self.refresh('scripts/file-input-source.py')
        with self.assertRaisesRegex(ValueError,'Implicit undeclared source'):H.load(self.root)

    def test_split_literal_native_path_is_a_real_dependency(self):
        path=self.root/'scripts/file-input-source.py';path.write_text(path.read_text()+"\nEMBEDDED=S.ROOT/'native'/'providers'/'unlisted.asm.inc'\n")
        self.refresh('scripts/file-input-source.py')
        with self.assertRaisesRegex(ValueError,'Implicit undeclared source'):H.load(self.root)

    def test_native_include_must_be_declared_and_in_identity(self):
        kernel='native/providers/file_input_readonly.asm.inc';extra='native/providers/unlisted.asm.inc'
        (self.root/extra).write_text('; isolated include fixture\n')
        path=self.root/kernel;path.write_bytes(path.read_bytes()+b'\nINCLUDE native/providers/unlisted.asm.inc\n')
        with self.assertRaisesRegex(ValueError,'INCLUDE dependency was not explicitly declared'):H.load(self.root)
        self.data['native_includes'][kernel]=[extra];self.write()
        with self.assertRaisesRegex(ValueError,'Implicit undeclared native INCLUDE'):H.load(self.root)

    def test_family_model_cannot_hide_dependencies_with_an_api_scope(self):
        self.data['api_scopes']['scripts/file-input-source.py']=['index'];self.invalid('cannot be hidden')

    def test_expanding_batch_verifier_api_requires_explicit_scope(self):
        path=self.root/'scripts/file-input-source.py'
        path.write_text(path.read_text()+"\ndef wider(S):\n a=S.module('full_batch', 'verify-batch-assembly.py')\n return a.verify(None,None)\n")
        self.refresh('scripts/file-input-source.py')
        with self.assertRaisesRegex(ValueError,'Undeclared consumed source API'):H.load(self.root)

    def test_unreachable_extra_source_rejected(self):
        name='scripts/unreachable.py';(self.root/name).write_text('value=1\n')
        self.data['tool_order'].append(name);self.data['shared_files'].append(name);self.refresh(name)
        with self.assertRaisesRegex(ValueError,'Unreachable extra source'):H.load(self.root)

    def test_helper_body_change_invalidates_full_identity(self):
        proof=H.snapshot(self.root);path=self.root/H.HELPER;path.write_bytes(path.read_bytes()+b'\n# changed helper implementation\n')
        with self.assertRaisesRegex(ValueError,'full source identity changed'):H.verify_snapshot(proof,self.root)

    def test_manifest_whitespace_is_still_full_file_identity(self):
        proof=H.snapshot(self.root);path=self.root/H.MANIFEST;path.write_bytes(path.read_bytes()+b'\n')
        self.assertEqual(H.load(self.root)['tool_files'],tuple(self.data['tool_order']))
        with self.assertRaisesRegex(ValueError,'full source identity changed'):H.verify_snapshot(proof,self.root)

    def test_unused_function_bytes_are_still_hashed(self):
        proof=H.snapshot(self.root);path=self.root/'scripts/verify-batch-assembly.py';path.write_bytes(path.read_bytes()+b'\n# full file changes still invalidate provider identity\n')
        with self.assertRaisesRegex(ValueError,'full source identity changed'):H.verify_snapshot(proof,self.root)

    def test_runtime_contract_is_separate_and_not_ignored(self):
        before=H.snapshot(self.root);name=before['contract']['runtime_contract_sources'][0]
        path=self.root/name;path.write_bytes(path.read_bytes()+b'\n; changed runtime contract source\n')
        after=H.snapshot(self.root)
        self.assertEqual(before['tool_sources'],after['tool_sources'])
        self.assertNotEqual(before['separately_required_runtime_sources'],after['separately_required_runtime_sources'])
        with self.assertRaises(ValueError):H.verify_snapshot(before,self.root)

    def test_no_implicit_eval_or_external_import(self):
        path=self.root/'scripts/file-input-source.py'
        for addition in ["\neval(dynamic)\n","\nimport nonstdlib_unpinned_dependency\n"]:
            original=path.read_bytes();path.write_bytes(original+addition.encode())
            with self.assertRaises(ValueError):H.load(self.root)
            path.write_bytes(original)

    def test_warm_cache_still_hashes_every_tool(self):
        with patch.object(H,'load',wraps=H.load) as audit:
            first=H.tools_identity(self.root);second=H.tools_identity(self.root)
            self.assertEqual(first,second);self.assertEqual(audit.call_count,1)
            with patch.object(H,'_identity_bytes',wraps=H._identity_bytes) as fresh:
                self.assertEqual(H.tools_identity(self.root),first)
                self.assertEqual(fresh.call_count,1)
                self.assertEqual(tuple(fresh.call_args.args[1]),tuple(self.data['tool_order']))

    def test_same_size_and_mtime_manifest_change_forces_audit(self):
        H.tools_identity(self.root);path=self.root/H.MANIFEST;old=path.stat()
        raw=path.read_bytes();changed=raw.replace(b'"schema": 1',b'"schema": 2',1)
        self.assertNotEqual(changed,raw);self.assertEqual(len(changed),len(raw))
        path.write_bytes(changed);os.utime(path,ns=(old.st_atime_ns,old.st_mtime_ns))
        self.assertEqual(path.stat().st_mtime_ns,old.st_mtime_ns)
        with patch.object(H,'load',wraps=H.load) as audit,self.assertRaisesRegex(ValueError,'Unsupported tool-manifest schema'):
            H.tools_identity(self.root)
        self.assertEqual(audit.call_count,1)

    def test_same_size_and_mtime_source_change_is_not_a_cache_hit(self):
        name='scripts/file-input-source.py';H.tools_identity(self.root);path=self.root/name;old=path.stat()
        raw=path.read_bytes();changed=raw.replace(b'Eight',b'eight',1)
        self.assertNotEqual(changed,raw);self.assertEqual(len(changed),len(raw))
        path.write_bytes(changed);os.utime(path,ns=(old.st_atime_ns,old.st_mtime_ns))
        with patch.object(H,'load',wraps=H.load) as audit:
            current=H.tools_identity(self.root);self.assertEqual(audit.call_count,1)
        self.assertEqual(current[name],H.sha256(changed))

    def test_cached_graph_is_not_mutable_by_callers(self):
        contract,identity=H._audited_identity(self.root);contract['family_sources'].clear();identity.clear()
        current,new_identity=H._audited_identity(self.root)
        self.assertEqual(set(current['family_sources']),set(self.data['families']))
        self.assertEqual(len(new_identity),len(self.data['tool_order']))


if __name__=='__main__':unittest.main()
