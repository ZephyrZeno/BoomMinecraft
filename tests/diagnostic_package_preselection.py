"""Package preselection must respect original loader, namespace, hash, and method budget."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('package_preselection', ROOT/'scripts/preselect-diagnostic-java.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def write(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')


class PackagePreselectionTests(unittest.TestCase):
    def fixture(self, root):
        batch, selection, plan = (root/n for n in ('batch','selection','plan'))
        for path in (batch,selection,plan):
            path.mkdir()
        classes = [(1,'bootstrap','java/util/A',2), (5,'bootstrap','java/lang/module/Descriptor',2),
                   (6,'bootstrap','java/lang/moduleExtra/Neighbor',1), (7,'vanilla-application','java/lang/module/Other',1),
                   (8,'bootstrap','java/lang/module/internal/Helper',1)]
        rows = [dict(id=i,name=name,origin=dict(loader=loader,sha256=str(i))) for i,loader,name,_ in classes]
        path = plan/'classes.jsonl'
        path.write_text(''.join(json.dumps(r)+'\n' for r in rows),encoding='utf-8')
        write(plan/'summary.json',dict(input_fingerprint='input',
              artifacts=dict(classes=dict(path=str(path),digest=dict(sha256=M.sha(path))))))
        archive = batch/'classes.zip'
        with zipfile.ZipFile(archive,'w') as z:
            for i,loader,name,count in classes:
                methods = [dict(id=i*10+j,assembly_emitted=True,code_sha256=str(i*10+j),stage='assembly_emitted_unlinked') for j in range(count)]
                methods.append(dict(id=i*10+9,assembly_emitted=False,code_sha256=None,stage='declaration'))
                z.writestr(f'classes/{i:06}.json',json.dumps(dict(class_id=i,name=name,source_sha256=str(i),methods=methods)))
        write(batch/'summary.json',dict(input_fingerprint='input',ir_identity='ir',
              shards=[dict(zip=dict(path=str(archive),digest=dict(sha256=M.sha(archive))))]))
        batch_hash = M.sha(batch/'summary.json')
        manifest = dict(batch=str(batch),plan=str(plan),source_batch_summary_sha256=batch_hash,batch_ir_identity='ir',
                        source_classes_sha256=M.sha(path),
                        selected_classes=[dict(class_id=1,source_sha256='1')])
        write(selection/'closure.json',manifest)
        (selection/'initialization-closure.asm').write_text('source',encoding='utf-8')
        write(selection/'selection-verification.json',dict(verified=True,diagnostic_only=True,source_closure_complete=False,
              closure_manifest_sha256=M.sha(selection/'closure.json'),closure_assembly_sha256=hashlib.sha256(b'source').hexdigest()))
        profile = root/'profile.json'
        write(profile,dict(source_batch_summary_sha256=batch_hash,admitted_methods=[99]))
        return batch, selection, plan, profile

    def test_package_and_loader_bounds_prioritize_generated_methods_without_claiming_execution(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.boom') as folder:
            root=Path(folder);batch,selection,plan,profile=self.fixture(root)
            result=M.preselect(batch,selection,profile,root/'out.json',2,['bootstrap:java/lang/module'])
            self.assertEqual(result['admitted_methods'],[50,51,99])
            evidence=result['source_only_preselection']
            self.assertEqual(evidence['matching_package_classes'],2)
            self.assertEqual(evidence['selected_package_classes'],[5])
            self.assertFalse(evidence['extra_methods_previously_executed'])
            self.assertEqual(evidence['extra_class_initialization_roots'],0)
            plain=M.preselect(batch,selection,profile,root/'plain.json',2)
            self.assertEqual(plain['admitted_methods'],[10,11,99])

    def test_changed_plan_or_selection_is_rejected(self):
        for target in ('classes','selection'):
            with self.subTest(target=target), tempfile.TemporaryDirectory(dir=ROOT/'.boom') as folder:
                root=Path(folder);batch,selection,plan,profile=self.fixture(root)
                file=plan/'classes.jsonl' if target=='classes' else selection/'closure.json'
                with file.open('ab') as stream:
                    stream.write(b' ')
                with self.assertRaises(ValueError):
                    M.preselect(batch,selection,profile,root/'out.json',2,['bootstrap:java/lang/module'])

    def test_empty_or_malformed_package_is_rejected(self):
        for package in ('bootstrap:','bootstrap:/java/lang','bootstrap:java/lang/moduleExtraExtra'):
            with self.subTest(package=package),tempfile.TemporaryDirectory(dir=ROOT/'.boom') as folder:
                root=Path(folder);batch,selection,plan,profile=self.fixture(root)
                with self.assertRaises(ValueError):
                    M.preselect(batch,selection,profile,root/'out.json',2,[package])

    def test_source_only_selection_can_cross_identical_Java_batches_and_rejects_changed_inputs(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.boom') as folder:
            root=Path(folder);batch,selection,plan,profile=self.fixture(root)
            derived=root/'derived';derived.mkdir()
            source=json.loads((batch/'summary.json').read_text())
            source['native_metadata_abi']=2
            write(derived/'summary.json',source)
            write(profile,dict(source_batch_summary_sha256=M.sha(derived/'summary.json'),admitted_methods=[99]))
            result=M.preselect(derived,selection,profile,root/'cross.json',2,['bootstrap:java/lang/module'])
            self.assertEqual(result['admitted_methods'],[50,51,99])
            reuse=result['source_only_preselection']['source_selection_reuse']
            self.assertFalse(reuse['native_bindings_reused'])
            self.assertFalse(reuse['current_selected_methods_previously_executed'])
            source['input_fingerprint']='different_input'
            write(derived/'summary.json',source)
            write(profile,dict(source_batch_summary_sha256=M.sha(derived/'summary.json'),admitted_methods=[99]))
            with self.assertRaisesRegex(ValueError,'source input or IR changed'):
                M.preselect(derived,selection,profile,root/'bad.json',2)


if __name__=='__main__':
    unittest.main()
