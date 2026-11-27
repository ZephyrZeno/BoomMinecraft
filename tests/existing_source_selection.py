"""Immutable source-envelope input shapes and actual read-set boundaries."""
import hashlib
import importlib.util
from pathlib import Path
import unittest
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('existing_selection_test',ROOT/'scripts/existing-source-selection.py')
E=importlib.util.module_from_spec(spec);spec.loader.exec_module(E)


class SealedSourceInputs(unittest.TestCase):
    def setUp(self):
        self.directory=ROOT/'.boom/existing-source-selection-tests'/uuid4().hex;self.directory.mkdir(parents=True)
        self.source=self.directory/'original.bin';self.source.write_bytes(b'original-source-and-COFF\0')

    def test_nested_and_flat_input_artifacts_and_legacy_sha1(self):
        record=E.S.artifact(self.source)
        self.assertEqual(E.checked(record),self.source)
        flat=dict(path=str(self.source),**record['digest'],sha1=hashlib.sha1(self.source.read_bytes()).hexdigest())
        self.assertEqual(E.checked(flat),self.source)
        with self.assertRaises(ValueError):E.checked(dict(flat,sha1='0'*40))
        with self.assertRaises(ValueError):E.checked(dict(flat,size=flat['size']+1))
        with self.assertRaises(ValueError):E.checked(dict(flat,sha256='0'*64))

    def test_actual_source_shard_and_code_reads_are_sealed_before_use(self):
        records={}
        code=self.directory/'imported.py';code.write_text('answer = 42\n')
        def seal(path):records[str(path)]=E.S.artifact(path)
        with E.ReadInputs(seal):
            self.assertEqual(self.source.read_bytes(),b'original-source-and-COFF\0')
            exec(compile(code.read_text(),str(code),'exec'),{})
            fresh=self.directory/'verifier-scratch.bin';fresh.write_bytes(b'fresh output');fresh.read_bytes()
        self.assertEqual(set(records),{str(self.source),str(code)})
        for record in records.values():E.checked(record)
        self.source.write_bytes(b'changed after verifier read')
        with self.assertRaises(ValueError):E.checked(records[str(self.source)])

    def test_overwriting_a_consumed_input_is_rejected(self):
        records=[]
        with E.ReadInputs(lambda path:records.append(E.S.artifact(path))):
            self.source.read_bytes()
            with self.assertRaises(ValueError):self.source.write_bytes(b'overwrite')
        self.assertEqual(self.source.read_bytes(),b'original-source-and-COFF\0')
        self.assertEqual(len(records),1)

    def test_completed_scope_does_not_capture_later_reads(self):
        records=[]
        with E.ReadInputs(lambda path:records.append(str(path))):self.source.read_bytes()
        after=self.directory/'later.bin';after.write_bytes(b'new invocation');after.read_bytes()
        self.assertEqual(records,[str(self.source)])


if __name__=='__main__':unittest.main()
