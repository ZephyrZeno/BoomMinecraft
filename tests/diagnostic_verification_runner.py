"""An interrupted or failing verifier must preserve its evidence on retry."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location('verification_runner',
        Path(__file__).resolve().parents[1] / 'scripts/run-diagnostic-verification.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class VerificationRunnerTests(unittest.TestCase):
    def test_silent_failure_then_successful_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            verifier = directory / 'verifier.py'
            receipt = directory / 'selection-verification.json'
            receipt.write_bytes(b'previous receipt')
            verifier.write_text('import os\nos._exit(27)\n', encoding='utf-8')
            with patch.object(runner, 'VERIFIER', verifier):
                failed = runner.verify(directory)
                self.assertEqual((failed['state'], failed['exit_code'], failed['exit_hex']), ('failed', 27, '0x0000001b'))
                self.assertEqual(Path(failed['stderr']).read_bytes(), b'')
                self.assertEqual(receipt.read_bytes(), b'previous receipt')
                verifier.write_text(
                    "import pathlib, sys\nsys.stdout.buffer.write(b'stdout\\xff')\nsys.stderr.buffer.write(b'stderr\\xfe')\n"
                    "pathlib.Path(sys.argv[-1]).write_bytes(b'{\"verified\":true,\"diagnostic_only\":true,\"source_closure_complete\":false}')\n",
                    encoding='utf-8')
                success = runner.verify(directory)
            self.assertEqual((success['state'], success['exit_code']), ('verified', 0))
            self.assertNotEqual(failed['directory'], success['directory'])
            self.assertEqual(json.loads((Path(failed['directory'])/'status.json').read_bytes()), failed)
            self.assertEqual(json.loads((directory/'selection-verification-status.json').read_bytes()), success)
            self.assertEqual((directory/'selection-verification.log').read_bytes(), b'stdout\xff')
            self.assertEqual((directory/'selection-verification.err').read_bytes(), b'stderr\xfe')
            self.assertEqual(receipt.read_bytes(), (Path(success['directory'])/'proof.json').read_bytes())

    def test_real_verifier_error_and_incomplete_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            error = runner.verify(directory)
            self.assertEqual(error['state'], 'failed')
            self.assertNotEqual(error['exit_code'], 0)
            self.assertIn(b'closure.json', Path(error['stderr']).read_bytes())
            verifier = directory / 'incomplete.py'
            verifier.write_text("import pathlib,sys\npathlib.Path(sys.argv[-1]).write_text('[]')\n", encoding='utf-8')
            with patch.object(runner, 'VERIFIER', verifier):
                incomplete = runner.verify(directory)
            self.assertEqual((incomplete['state'], incomplete['exit_code']), ('failed', 0))
            self.assertFalse((directory/'selection-verification.json').exists())


if __name__ == '__main__':
    unittest.main()
