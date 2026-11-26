"""Reject changed/mixed native frame dependencies before diagnostic linking."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('diagnostic_provider_projection_tests',ROOT/'scripts/diagnostic-closure.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


class DiagnosticProviderProjectionTests(unittest.TestCase):
    def test_conflicting_native_frame_dependencies_are_rejected(self):
        packs=[dict(manifest=dict(frame_overlay=dict(manifest=dict(path='first')))),
               dict(manifest=dict(frame_overlay=dict(manifest=dict(path='second'))))]
        with self.assertRaisesRegex(ValueError,'conflicting'):M.frame_overlay(packs)

    def test_changed_dependent_object_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.boom') as directory:
            path=Path(directory)/'data.obj';path.write_bytes(b'original')
            record=dict(path=str(path),digest=dict(size=8,sha256=hashlib.sha256(b'original').hexdigest()))
            self.assertEqual(M.checked_provider_record(record),path)
            path.write_bytes(b'modified')
            with self.assertRaisesRegex(ValueError,'changed'):M.checked_provider_record(record)

    def test_unselected_invocation_family_adds_no_callsite_data(self):
        pack=dict(manifest=dict(family='normal-constructor-invocation-v1'))
        self.assertEqual(M.constructor_selection([pack],set(),set(),set()),('',set(),set(),None))

    def test_base_sha1_is_optional_but_sha256_and_size_must_agree(self):
        left=dict(path=str(ROOT/'target/data.obj'),digest=dict(size=8,sha256='a'))
        right=dict(path=left['path'],digest=dict(size=8,sha256='a',sha1='older-base-format'))
        self.assertTrue(M.same_provider_record(left,right))
        right['digest']['sha256']='different'
        self.assertFalse(M.same_provider_record(left,right))


if __name__=='__main__':unittest.main()
