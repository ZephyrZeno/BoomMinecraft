"""Rejection tests for the independent AMD64 object artifact verifier."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("batch_verifier", ROOT/"scripts/verify-batch-assembly.py")
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


def object_bytes(symbols, machine=0x8664):
    table, strings = bytearray(), bytearray(b"\0"*4)
    for name, section in symbols:
        raw = name.encode("ascii")
        if len(raw) > 8:
            encoded = struct.pack("<II", 0, len(strings))
            strings.extend(raw+b"\0")
        else:
            encoded = raw.ljust(8, b"\0")
        table.extend(struct.pack("<8sIhHBB", encoded, 0, section, 0, 2, 0))
    struct.pack_into("<I", strings, 0, len(strings))
    return bytearray(struct.pack("<HHIIIHH", machine, 1, 0, 60, len(symbols), 0, 0)
                     + b"\0"*40+table+strings)


class BatchObjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/"test.obj"

    def symbols(self, data):
        self.path.write_bytes(data)
        return VERIFIER.coff_symbols(self.path)

    def test_real_symbol_records_distinguish_definitions_and_imports(self):
        defined, undefined = self.symbols(object_bytes([
            ("boom_m7", 1), ("boom_m7_body", 1), ("boom_batch_call_1_3_182", 0)]))
        self.assertEqual(defined, {"boom_m7", "boom_m7_body"})
        self.assertEqual(undefined, {"boom_batch_call_1_3_182"})

    def test_rejects_wrong_machine_and_foreign_runtime_import(self):
        with self.assertRaisesRegex(ValueError, "AMD64"):
            self.symbols(object_bytes([("boom_m7", 1)], machine=0x14c))
        with self.assertRaisesRegex(ValueError, "foreign runtime"):
            self.symbols(object_bytes([("JNI_CreateJavaVM", 0)]))

    def test_own_runtime_IAT_reference_retains_its_symbol_identity(self):
        defined,undefined=self.symbols(object_bytes([('boom_service',1),('__imp_boom_scoped_close_unavailable',0)]))
        self.assertEqual(defined,{'boom_service'})
        self.assertEqual(undefined,{'__imp_boom_scoped_close_unavailable'})

    def test_IAT_alias_does_not_allow_JVM_or_arbitrary_OS_imports(self):
        for name in ('__imp_JNI_CreateJavaVM','__imp_GetProcAddress'):
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'foreign runtime'):
                self.symbols(object_bytes([(name,0)]))

    def test_os_wait_imports_need_explicit_per_module_allowlist(self):
        self.path.write_bytes(object_bytes([("WaitOnAddress", 0), ("WakeByAddressAll", 0)]))
        with self.assertRaisesRegex(ValueError, "foreign runtime"):
            VERIFIER.coff_symbols(self.path)
        self.assertEqual(VERIFIER.coff_symbols(self.path, frozenset(("WaitOnAddress", "WakeByAddressAll")))[1],
                         {"WaitOnAddress", "WakeByAddressAll"})
        self.path.write_bytes(object_bytes([("JNI_CreateJavaVM", 0)]))
        with self.assertRaisesRegex(ValueError, "foreign runtime"):
            VERIFIER.coff_symbols(self.path, frozenset(("WaitOnAddress", "WakeByAddressAll")))

    def test_rejects_unterminated_name_and_invalid_auxiliary_count(self):
        data = object_bytes([("boom_long_symbol", 1)])
        data[-1] = ord("x")
        with self.assertRaisesRegex(ValueError, "Unterminated"):
            self.symbols(data)
        data = object_bytes([("boom_m7", 1)])
        data[60+17] = 1
        with self.assertRaisesRegex(ValueError, "metadata"):
            self.symbols(data)

    def test_rejects_changed_object_bytes(self):
        self.path.write_bytes(object_bytes([("boom_m7", 1)]))
        metadata = dict(path=str(self.path), digest=VERIFIER.file_digest(self.path))
        self.path.write_bytes(self.path.read_bytes()+b"changed")
        with self.assertRaisesRegex(ValueError, "Artifact changed"):
            VERIFIER.artifact(self.path.parent, metadata)


if __name__ == "__main__":
    unittest.main()
