"""Native manifest inputs retain strict legacy identity without mixing digest schemas."""
from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('native_input_artifact_model',ROOT/'scripts/vm-entry-source.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


class NativeInputArtifacts(unittest.TestCase):
    def test_original_jar_with_sha1_remains_a_native_sealed_input(self):
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'original.jar';file.write_bytes(b'locked source archive bytes')
            canonical=M.S.artifact(file);legacy=deepcopy(canonical)
            legacy['digest']['sha1']=hashlib.sha1(file.read_bytes()).hexdigest()
            self.assertEqual(M.native_input_artifact(legacy),canonical)
            self.assertEqual(M.native_input_artifact(canonical),canonical)
            legacy['digest']['sha1']='0'*40
            with self.assertRaisesRegex(ValueError,'SHA1 changed'):M.native_input_artifact(legacy)
            file.write_bytes(b'changed source archive bytes')
            with self.assertRaisesRegex(ValueError,'input changed'):M.native_input_artifact(canonical)


if __name__=='__main__':unittest.main()
