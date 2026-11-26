"""Diagnostic source closures must never resolve an uncertified sparse object."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).resolve().parents[1]/'scripts'/(name+'.py'))
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


C=load('closure-batch-artifacts')
R=load('refresh-unsafe-field-batch')


class ClosureBatchArtifactTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root=Path(directory.name).resolve()
        self.base=self.root/'base'
        self.batch=self.root/'derived'
        for root in (self.base,self.batch):
            for sub in ('string-literals','unsafe-fields'):
                (root/sub).mkdir(parents=True)
        self.old=self.base/'string-literals/0000.obj'
        self.new=self.batch/'unsafe-fields/0002.obj'
        self.old.write_bytes(b'old supplied object')
        self.new.write_bytes(b'new supplied object')
        self.meta={'units':[R.artifact(p) for p in (self.old,self.new)]}
        self.resolve=C.source_records(self.meta,R.sparse_artifacts(self.base,self.batch))

    def test_keeps_dense_fixed_root_and_requires_derivation_for_sparse_receipt(self):
        coff=SimpleNamespace(artifact=R.A.artifact)
        self.assertIsNone(C.configure(coff,self.base,self.meta))
        self.assertIs(coff.artifact,R.A.artifact)
        (self.batch/'verification.json').write_text('{"sparse_original_vm_image_home":{}}')
        with self.assertRaisesRegex(ValueError,'Missing source batch derivation'):
            C.configure(coff,self.batch,self.meta)

    def test_mixed_certified_locations_require_exact_module_and_root(self):
        old,new=self.meta['units']
        self.assertEqual(self.resolve(self.batch,old,'string-literals'),self.old)
        self.assertEqual(self.resolve(self.batch,new,'unsafe-fields'),self.new)
        for directory in ('unsafe-fields',str(self.old.parent),'../base/string-literals'):
            with self.subTest(directory=directory), self.assertRaises(ValueError):
                self.resolve(self.batch,old,directory)
        with self.assertRaises(ValueError):
            self.resolve(self.base,old,'string-literals')

    def test_changed_digest_changed_bytes_and_unlisted_file_are_rejected(self):
        old=self.meta['units'][0]
        bad=dict(old,digest=dict(old['digest'],sha256='0'*64))
        with self.assertRaisesRegex(ValueError,'digest differs'):
            self.resolve(self.batch,bad,'string-literals')
        self.old.write_bytes(b'bad supplied object')
        with self.assertRaisesRegex(ValueError,'Sparse artifact digest differs'):
            self.resolve(self.batch,old,'string-literals')
        unlisted=self.old.with_name('0001.obj')
        unlisted.write_bytes(self.new.read_bytes())
        with self.assertRaisesRegex(ValueError,'absent'):
            self.resolve(self.batch,R.artifact(unlisted),'string-literals')

    def test_even_a_record_in_the_summary_cannot_escape_the_producer_roots(self):
        other=self.root/'sibling'/'string-literals'/'0000.obj'
        other.parent.mkdir(parents=True)
        other.write_bytes(self.old.read_bytes())
        record=R.artifact(other)
        resolve=C.source_records([record],R.sparse_artifacts(self.base,self.batch))
        with self.assertRaisesRegex(ValueError,'escapes'):
            resolve(self.batch,record,'string-literals')

    def test_jcls_delegation_preserves_explicit_provenance_and_summary_membership(self):
        (self.batch/'boot-unnamed-derivation.json').write_text('{}')
        coff=SimpleNamespace()
        provider=SimpleNamespace(verified_resolver=lambda *_:(R.sparse_artifacts(self.base,self.batch),{'scope':'JCLS test'}))
        with patch.object(C,'module',return_value=provider):
            proof=C.configure(coff,self.batch,self.meta)
        self.assertEqual(proof['scope'],'JCLS test')
        self.assertEqual(len(proof['closure_resolver_sha256']),64)
        self.assertEqual(coff.artifact(self.batch,self.meta['units'][0],'string-literals'),self.old)

    def test_full_scope_and_derived_summary_are_bound_before_acceptance(self):
        path=self.batch/'summary.json'
        path.write_text(json.dumps(self.meta))
        summary=R.artifact(path)
        base={'summary':{'digest':{'sha256':'base'}}}
        data=dict(base_batch=str(self.base),plan=str(self.root/'plan'),accepted_base=base,derivative=summary)
        (self.batch/'unsafe-field-derivation.json').write_text(json.dumps(data))
        scope=dict(base_summary=base['summary'],derived_summary=summary)
        full={k:{'verified':True} for k in ('unsafe_fields','unsafe_memory','class_lookup','frames','properties')}
        full.update(verified=False,sparse_original_vm_image_home=scope)
        with patch.object(C,'module',return_value=R),patch.object(R,'ART',self.root):
            receipt=self.batch/'verification.json'
            receipt.write_text(json.dumps(full))
            with self.assertRaisesRegex(ValueError,'full sparse source'):
                C.configure(SimpleNamespace(),self.batch,self.meta)
            full['verified']=True
            receipt.write_text(json.dumps(full))
            path.write_text('{}')
            with self.assertRaisesRegex(ValueError,'summary differs'):
                C.configure(SimpleNamespace(),self.batch,self.meta)


if __name__=='__main__':
    unittest.main()
