"""Checks the independent symbolic IR verifier's rejection behavior."""
import copy
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ir_verifier", ROOT/"scripts/verify-translation-ir.py")
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class IRVerifierTests(unittest.TestCase):
    def setUp(self):
        self.source = dict(bytes=bytes([0x1a, 0x99, 0, 5, 0x04, 0xac, 0x03, 0xac]),
                           max_stack=1, max_locals=1, handlers=[], lines=[])
        self.body = dict(max_stack=1, max_locals=1, code_length=8,
                         instructions=list(VERIFIER.stream(self.source["bytes"])),
                         handlers=[], contains_legacy_subroutines=False,
                         blocks=[dict(start=0, end=4, first_instruction=0, instruction_count=2,
                                      successors=[4, 6], handlers=[]),
                                 dict(start=4, end=6, first_instruction=2, instruction_count=2,
                                      successors=[], handlers=[]),
                                 dict(start=6, end=8, first_instruction=4, instruction_count=2,
                                      successors=[], handlers=[])])

    def test_accepts_operand_preserving_branch_ir(self):
        VERIFIER.verify_body(self.body, self.source)

    def test_rejects_changed_branch_operand(self):
        self.body["instructions"][1]["operand"]["Branch"] = 4
        with self.assertRaisesRegex(ValueError, "instruction/operand differs"):
            VERIFIER.verify_body(self.body, self.source)

    def test_rejects_changed_control_flow(self):
        self.body["blocks"][0]["successors"] = [4]
        with self.assertRaisesRegex(ValueError, "block edges/protected region differ"):
            VERIFIER.verify_body(self.body, self.source)

    def test_rejects_changed_exception_precedence(self):
        self.source["handlers"] = [dict(start=0, end=4, target=6, catch_type=None),
                                   dict(start=0, end=4, target=4, catch_type=None)]
        self.body["handlers"] = copy.deepcopy(list(reversed(self.source["handlers"])))
        with self.assertRaisesRegex(ValueError, "exception row order"):
            VERIFIER.verify_body(self.body, self.source)

    def test_named_and_multidimensional_signature_is_preserved(self):
        actual = VERIFIER.descriptor("(J[[Lp/Missing;)Ljava/lang/Other;")
        self.assertEqual(actual["parameters"][1], {"Array": dict(dimensions=2, element={"Object": "p/Missing"})})
        self.assertEqual(actual["result"], {"Object": "java/lang/Other"})


if __name__ == "__main__":
    unittest.main()
