"""Focused source-transform checks; no compilation or guest execution."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[1]
ROOT = next(path for path in Path(__file__).resolve().parents
            if (path / 'native/entry/vm_process.asm.inc').is_file())
ACTUAL_ENTRY = ROOT / '.boom/vm-entry-images/v211-current35-jimage-overlay-f/vm-entry-overlay.asm'
spec = importlib.util.spec_from_file_location('signal_shutdown_source_under_test', HERE / 'scripts/main-signal-shutdown-source.py')
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)


class SignalShutdownSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'native/entry/vm_process.asm.inc').read_text(encoding='utf-8')

    def test_native_process_inverse_all_bytes(self):
        out, model = G.derive(self.source)
        self.assertEqual(G.inverse(out, model), self.source)
        self.assertEqual(out.count(model['original_signal_block']), 1)

    @unittest.skipUnless(ACTUAL_ENTRY.is_file(), 'Isolated frozen-f entry is unavailable')
    def test_actual_f_entry_also_reversible(self):
        raw = ACTUAL_ENTRY.read_text(encoding='utf-8')
        out, model = G.derive(raw)
        self.assertEqual(G.inverse(out, model), raw)

    def test_complete_signal_block_is_after_owned_reap_before_cleanup(self):
        out, model = G.derive(self.source)
        self.assertLess(out.index(G.OWNED_START), out.index(G.AFTER_JOIN))
        self.assertLess(out.index(G.AFTER_JOIN), out.index(G.SIGNAL_START))
        self.assertLess(out.index(G.SIGNAL_START), out.index(G.CLEANUP_START))
        self.assertIn(G.AFTER_JOIN + model['original_signal_block'] + G.SECOND_CLOSE + G.CLEANUP_START, out)

    def test_second_close_real_call_nonzero_only_and_no_new_import(self):
        out, model = G.derive(self.source)
        self.assertEqual(out.count(' call boom_provider_threads_close\n'), self.source.count(' call boom_provider_threads_close\n') + 1)
        self.assertIn(' test eax,eax\n jz vpe_post_signal_threads_closed\n mov DWORD PTR [rsp+72],eax\n', G.SECOND_CLOSE)
        self.assertNotIn('xor', G.SECOND_CLOSE)
        self.assertEqual(model['additional_external_imports'], [])

    def test_owned_deadline_and_all_failure_guards_identical(self):
        out, _ = G.derive(self.source)
        owned = self.source[self.source.index(G.OWNED_START):self.source.index(G.AFTER_JOIN)+len(G.AFTER_JOIN)]
        self.assertIn(owned, out)
        self.assertEqual(self.source[self.source.index(G.CLEANUP_START):], out[out.index(G.CLEANUP_START):])

    def test_reject_double_application(self):
        out, _ = G.derive(self.source)
        with self.assertRaises(ValueError):
            G.derive(out)

    def test_missing_or_duplicate_anchor_rejected(self):
        for source in (self.source.replace(G.AFTER_JOIN, '', 1), self.source + G.AFTER_JOIN):
            with self.assertRaises(ValueError):
                G.derive(source)

    def test_inverse_source_or_model_tamper_rejected(self):
        out, model = G.derive(self.source)
        with self.assertRaises(ValueError):
            G.inverse(out + '\n', model)
        model['second_close_text'] = model['second_close_text'].replace('test eax,eax', 'xor eax,eax')
        with self.assertRaises(ValueError):
            G.inverse(out, model)


if __name__ == '__main__':
    unittest.main()
