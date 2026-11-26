import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

S=importlib.util.spec_from_file_location('seed_verifier',Path(__file__).resolve().parents[1]/'scripts/seed-diagnostic-profile.py');M=importlib.util.module_from_spec(S);S.loader.exec_module(M)


def source():
    return dict(class_id=2,source_sha256='class',methods=[dict(id=1,name='run',descriptor='()V',code_sha256='code',assembly_emitted=True,stage='assembly_emitted_unlinked')])


class DiagnosticSeedTests(unittest.TestCase):
    def test_identical_entries_need_no_cross_entry_marker(self):
        self.assertIsNone(M.entry_reuse(['bootstrap:example/A:run:()V'],['bootstrap:example/A:run:()V'],False))

    def test_changed_entry_requires_explicit_selection_reuse(self):
        with self.assertRaisesRegex(ValueError,'roots/entries differ'):M.entry_reuse(['old'],['new'],False)

    def test_cross_entry_reuse_does_not_claim_new_entry_execution(self):
        result=M.entry_reuse(['old'],['new'],True)
        self.assertEqual(result['previous_entries'],['old']);self.assertEqual(result['requested_entries'],['new'])
        self.assertFalse(result['new_entries_previously_executed']);self.assertFalse(result['full_VM_bootstrap'])

    def test_cross_entry_reuse_rejects_empty_or_duplicate_entries(self):
        for entries in ([],['new','new']):
            with self.subTest(entries=entries),self.assertRaisesRegex(ValueError,'roots/entries differ'):M.entry_reuse(['old'],entries,True)

    def test_identical_original_java_is_eligible(self):M.compatible_methods(source(),source(),[1])

    def test_compiler_change_does_not_change_locked_source_identity(self):
        M.identity(dict(input_fingerprint='lock',ir_identity='ir',compiler_sha256='old'),dict(input_fingerprint='lock',ir_identity='ir',compiler_sha256='new'))

    def test_input_or_ir_change_rejected(self):
        for key in ('input_fingerprint','ir_identity'):
            a=dict(input_fingerprint='lock',ir_identity='ir');b=dict(a);b[key]='changed'
            with self.subTest(key=key),self.assertRaises(ValueError):M.identity(a,b)

    def test_native_failed_or_unverified_method_cannot_be_admitted(self):
        for key,value in [('assembly_emitted',False),('code_sha256',None),('stage','declaration')]:
            a=source();a['methods'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):M.compatible_methods(source(),a,[1])

    def test_changed_class_code_or_descriptor_rejected(self):
        for key,value in [('class_id',3),('source_sha256','changed')]:
            a=source();a[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):M.compatible_methods(source(),a,[1])
        for key,value in [('code_sha256','changed'),('name','other'),('descriptor','()I')]:
            a=source();a['methods'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):M.compatible_methods(source(),a,[1])

    def test_unknown_method_rejected(self):
        with self.assertRaises(ValueError):M.compatible_methods(source(),source(),[7])

    def test_archive_cache_keeps_class_provenance_and_rechecks_bytes(self):
        base=M.ROOT/'.boom'
        base.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base) as tmp:
            path=Path(tmp)/'classes.zip'
            with zipfile.ZipFile(path,'w') as z:z.writestr('classes/000002.json',json.dumps(source()))
            record=dict(path=str(path),digest=dict(sha256=M.digest(path)))
            summary=dict(shards=[dict(zip=record)])
            cache=M.SeedSources()
            self.assertEqual(cache.read(summary,{2})[2],source())
            with self.assertRaisesRegex(ValueError,'Missing source class'):cache.read(summary,{3})
            bad=copy.deepcopy(summary);bad['shards'][0]['zip']['digest']['sha256']='different'
            with self.assertRaisesRegex(ValueError,'archive changed'):cache.read(bad,{2})
            cache.verify()
            with path.open('ab') as out:out.write(b'changed')
            with self.assertRaisesRegex(ValueError,'during replay'):cache.verify()


if __name__=='__main__':unittest.main()
