"""Automatic admission must use reached, already generated Java only."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

SPEC=importlib.util.spec_from_file_location('diagnostic_profile',Path(__file__).resolve().parents[1]/'scripts/update-diagnostic-profile.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)


class DiagnosticProfileTests(unittest.TestCase):
    def fixture(self,root):
        method=dict(id=10,name='size',descriptor='()I',code_sha256='code',stage='assembly_emitted_unlinked',assembly_emitted=True,assembly_unit=0)
        other=dict(method,id=11,name='put');native=dict(method,id=12,name='native',assembly_emitted=False,code_sha256=None)
        archive=Path(root)/'shard.zip'
        with zipfile.ZipFile(archive,'w') as z:z.writestr('classes/000001.json',json.dumps(dict(source_sha256='source',methods=[method,other,native])))
        (Path(root)/'summary.json').write_text(json.dumps(dict(shards=[dict(zip=dict(path=str(archive)))])),encoding='utf-8')
        event=dict(diagnostic_only=True,fault=dict(category=1,class_id=1,source_sha256='source',method=method))
        execution=Path(root)/'execution.json';execution.write_text(json.dumps(event),encoding='utf-8')
        return event,execution

    def test_reached_class_admission_keeps_native_missing(self):
        with tempfile.TemporaryDirectory() as root:
            event,p=self.fixture(root);r=M.update(root,p,[9])
            self.assertEqual(r['admitted_methods'],[9,10,11]);self.assertEqual(r['native_implementations_added'],0)

    def test_unavailable_or_modified_target_cannot_be_admitted(self):
        for change in ('category','code','class'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as root:
                e,p=self.fixture(root)
                if change=='category':e['fault']['category']=2
                elif change=='code':e['fault']['method']['code_sha256']='modified'
                else:e['fault']['source_sha256']='modified'
                p.write_text(json.dumps(e),encoding='utf-8')
                with self.assertRaises(ValueError):M.update(root,p,[])

    def test_initialization_admission_requires_exact_source_state(self):
        with tempfile.TemporaryDirectory() as root:
            state=dict(class_id=2,source_sha256='source',diagnostic=None,fields=[],initializer=None,dependencies=[])
            archive=Path(root)/'states.zip'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('classes.jsonl',json.dumps(state)+'\n')
            (Path(root)/'summary.json').write_text(json.dumps(dict(class_state=dict(index=dict(path=str(archive))))))
            event=dict(diagnostic_only=True,fault=dict(category=5,class_id=2,source_sha256='source',symbol='boom_batch_initialize_2',initialization=state))
            p=Path(root)/'execution.json';p.write_text(json.dumps(event));r=M.update(root,p,[9],[1])
            self.assertEqual(r['admitted_methods'],[9]);self.assertEqual(r['admitted_classes'],[1,2]);self.assertEqual(r['native_implementations_added'],0)
            event['fault']['initialization']['dependencies']=[3];p.write_text(json.dumps(event))
            with self.assertRaises(ValueError):M.update(root,p,[9])

    def test_independent_thread_admissions_follow_native_rows_and_keep_each_owner(self):
        directory=Path(__file__).resolve().parents[1]/'.boom/vm-entry-images'
        directory.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=directory) as tmp:
            root=Path(tmp);event,path=self.fixture(root)
            main=dict(event['fault'],id=1)
            other_method=dict(main['method'],id=20)
            first=dict(main,id=2,class_id=2,source_sha256='second',method=other_method)
            with zipfile.ZipFile(root/'shard.zip','a') as z:
                z.writestr('classes/000002.json',json.dumps(dict(source_sha256='second',methods=[other_method])))
            image=root/'image';image.mkdir()
            (root/'native-execution-directory.txt').write_text(str(image),encoding='utf-8')
            words=[0]*80;words[0:2]=[0x52454d56,8];words[7:9]=[2,2];words[74]=0xb001;words[78]=1
            raw=struct.pack('<80I',*words);(image/'vm-entry-status.bin').write_bytes(raw)
            sha=lambda data:hashlib.sha256(data).hexdigest()
            table=json.dumps(dict(rows=[main,first])).encode()
            (root/'diagnostic.json').write_bytes(table)
            proof=json.dumps(dict(verified=True,diagnostic_only=True,diagnostic_manifest_sha256=sha(table))).encode()
            (root/'selection-verification.json').write_bytes(proof)
            manifest=json.dumps(dict(baseline_directory=str(root),accepted_source_verification_sha256=sha(proof))).encode()
            (image/'vm-entry.json').write_bytes(manifest)
            native=json.dumps(dict(verified=True,source_manifest_sha256=sha(manifest))).encode()
            (image/'verification.json').write_bytes(native)
            event.update(fault=main,first_process_fault=first,main_source_row=1,first_row=2,
                         source_admission_rows=[1,2],native_report_sha256=sha(raw),source_verification_sha256=sha(native))
            path.write_text(json.dumps(event))
            result=M.update(root,path,[9])
            self.assertEqual(result['admitted_methods'],[9,10,11,20])
            self.assertEqual(result['method_admission_owners'],{'10':1,'11':1,'20':2})
            self.assertEqual(result['reached_source_rows'],[1,2])
            for change in (dict(source_admission_rows=[1]),dict(main_source_row=2),dict(first_process_fault=main)):
                path.write_text(json.dumps(dict(event,**change)))
                with self.assertRaises(ValueError):M.update(root,path,[9])
            path.write_text(json.dumps(event));(image/'vm-entry-status.bin').write_bytes(raw[:-1])
            with self.assertRaises(ValueError):M.update(root,path,[9])


if __name__=='__main__':unittest.main()
