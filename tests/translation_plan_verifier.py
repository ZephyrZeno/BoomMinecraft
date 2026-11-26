r"""Run with D:\Dev\Python312\python.exe tests/translation_plan_verifier.py."""
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
import uuid

PROJECT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "plan_verifier", PROJECT / "scripts/verify-translation-plan.py")
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class PlanVerifierTests(unittest.TestCase):
    def setUp(self):
        self.root = PROJECT / ".boom/translation-plan-verifier-tests" / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.summary = dict(
            mode="inventory_and_plan_only", compiled_methods=0, game_started=False,
            world_created=False, full_game_ready=False, type_layout_and_link_verified=False,
            native_catalog_is_complete=False, classes=1, class_parse_failures=0,
            java_base_classes=0, application_classes=1, methods=4, java_methods=4,
            native_methods=0, abstract_methods=0, structurally_scanned_java_methods=4,
            native_binding_candidates=0, native_without_catalog_entry=0,
            dependency_edges=4, startup_seed_methods=[0], main_seed_methods=[3],
            conservative_startup_methods=4, conservative_main_methods=1,
            batches=3, compatibility_groups=0, artifacts={})
        self.write("classes", [dict(id=0, name="p/C", parse_error=None,
                                    origin=dict(loader="app", sha256="a" * 64),
                                    method_ids=[0, 1, 2, 3])])
        self.write("methods", [dict(
            id=i, class_id=0, class_sha256="a" * 64,
            symbol=dict(loader="app", owner="p/C", name=f"m{i}", descriptor="()V"),
            assembly_emitted=False, type_layout_and_link_verified=False,
            kind="java_pending_lowering", code_sha256="b" * 64, access=9,
            structural_scan_complete=True, conservative_startup_reachable=True,
            conservative_main_reachable=(i == 3), problems=[]) for i in range(4)])
        self.write("dependencies", [dict(method_id=i, dependencies=edges)
                                     for i, edges in enumerate([[1], [2], [1, 3], []])])
        self.write("batches", [dict(id=i, method_ids=nodes, dependency_batches=deps,
                                    startup_priority=True, main_priority=(i == 0))
                               for i, (nodes, deps) in enumerate([([3], []), ([1, 2], [0]), ([0], [1])])])
        self.write("compatibility", [])
        self.write("opcodes", [dict(opcode=177, instructions=4)])
        self.save()

    def write(self, name, records):
        path = self.root / f"{name}.jsonl"
        data = "".join(json.dumps(row) + "\n" for row in records).encode("utf-8")
        path.write_bytes(data)
        self.summary["artifacts"][name] = dict(path=str(path), digest=dict(
            size=len(data), sha1=hashlib.sha1(data).hexdigest(),
            sha256=hashlib.sha256(data).hexdigest()))

    def save(self):
        (self.root / "summary.json").write_text(json.dumps(self.summary), encoding="utf-8")

    def test_accepts_complete_cyclic_dependency_plan(self):
        self.assertTrue(VERIFIER.verify(self.root)["verified"])

    def test_rejects_corrupt_artifact(self):
        (self.root / "opcodes.jsonl").write_bytes(b"{}\n")
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            VERIFIER.verify(self.root)

    def test_rejects_dependency_omission_even_with_valid_hash(self):
        self.write("batches", [dict(id=i, method_ids=nodes, dependency_batches=[],
                                    startup_priority=True, main_priority=(i == 0))
                               for i, nodes in enumerate([[3], [1, 2], [0]])])
        self.save()
        with self.assertRaisesRegex(ValueError, "Batch dependencies differ"):
            VERIFIER.verify(self.root)

    def test_rejects_missing_method_even_with_valid_hash(self):
        self.write("classes", [dict(id=0, name="p/C", parse_error=None,
                                    origin=dict(loader="app", sha256="a" * 64),
                                    method_ids=[0, 1, 2])])
        self.save()
        with self.assertRaisesRegex(ValueError, "missing from its defining class"):
            VERIFIER.verify(self.root)


if __name__ == "__main__":
    unittest.main()
