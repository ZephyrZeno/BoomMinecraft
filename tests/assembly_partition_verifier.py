"""Reject dropped or changed method bytes during assembler-unit partitioning."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("partition", Path(__file__).resolve().parents[1]/"scripts/verify-assembly-partition.py")
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class PartitionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.old, self.new = Path(temp.name)/"old", Path(temp.name)/"new"
        for root in (self.old, self.new): (root/"shards").mkdir(parents=True)
        self.first = b"boom_m0 PROC\n ret\nboom_m0 ENDP\n\n"
        self.second = b".const\nboom_table QWORD 42\n.code\nboom_m1 PROC\n ret\nboom_m1 ENDP\n\n"
        self.module(self.old/"shards/00000.asm", self.first+self.second)
        for index, body in enumerate((self.first, self.second)):
            self.module(self.new/"shards"/f"00000-{index:04}.asm", body)
        (self.new/"summary.json").write_text(json.dumps(dict(schema=2, shards=[dict(id=0, units=[
            dict(assembly=dict(path=f"00000-{i:04}.asm")) for i in range(2)])])), encoding="utf-8")

    def module(self, path, body):
        path.write_bytes(b"option casemap:none\n.code\n"+body+b"\nEND\n")

    def test_preserves_function_and_exception_data_section_bytes(self):
        result = VERIFIER.verify(self.old, self.new)
        self.assertTrue(result["verified"])
        self.assertEqual(result["assembly_units"], 2)
        self.assertEqual(result["preserved_body_bytes"], len(self.first)+len(self.second))

    def test_rejects_changed_instruction(self):
        self.module(self.new/"shards/00000-0000.asm", self.first.replace(b"ret", b"nop"))
        with self.assertRaisesRegex(ValueError, "method bodies changed"):
            VERIFIER.verify(self.old, self.new)

    def test_rejects_dropped_method_or_data(self):
        self.module(self.new/"shards/00000-0001.asm", b"")
        with self.assertRaisesRegex(ValueError, "method bodies changed"):
            VERIFIER.verify(self.old, self.new)


if __name__ == "__main__": unittest.main()
