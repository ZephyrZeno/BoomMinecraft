"""Test-only post-System3 report rules; no native execution is inferred here."""
import importlib.util
from pathlib import Path
import struct
import unittest


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('component_report_test',ROOT/'scripts/stack-walk-component.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)


class ComponentReportRules(unittest.TestCase):
    def reports(self):
        raw,probe=bytearray(544),bytearray(128)
        def u(at,value):struct.pack_into('<I',raw,at,value)
        def q(at,value):struct.pack_into('<Q',raw,at,value)
        u(0,0x52454d56);u(4,13);u(52,2);u(64,7);u(72,1);u(76,1)
        for at in (144,148,272,276,280,320,324,328,400,404,408,448,452,512,516):u(at,1)
        for at in (152,168,176):q(at,1)
        for at in (128,208,216,224,232):q(at,2)
        u(288,1);u(292,2);u(380,6);u(520,2);u(524,4);q(504,128)
        struct.pack_into('<II',probe,0,1,1)
        for at,value in ((56,1),(64,1),(80,2),(88,1)):struct.pack_into('<Q',probe,at,value)
        return raw,probe

    def test_ordinary_phase3_snapshot_is_separate_from_later_test(self):
        raw,probe=self.reports();result=C.decode(raw,probe,0,{'rows':[]})
        self.assertTrue(result['cold_constructor_completed']);self.assertTrue(result['original_Java_callback_execution_verified'])
        self.assertFalse(result['native_8_OS_execution_verified']);self.assertFalse(result['full_selection_reverified'])

    def test_real_source_stop_scope_keeps_earlier_System123_success(self):
        raw,probe=self.reports()
        for at,value in ((12,45057),(28,2),(32,7),(72,0),(80,86),(296,45057),(300,81),(304,41700)):
            struct.pack_into('<I',raw,at,value)
        struct.pack_into('<I',probe,4,0);struct.pack_into('<IIII',probe,16,45057,81,41700,0)
        struct.pack_into('<Q',probe,64,0);struct.pack_into('<Q',probe,88,0)
        result=C.decode(raw,probe,86,{'rows':[dict(id=7,symbol='boom_m41700',category=2)]})
        self.assertTrue(result['original_System123_completed']);self.assertFalse(result['cold_constructor_completed'])
        self.assertFalse(result['original_Java_callback_execution_verified']);self.assertEqual(result['first_source_fault']['id'],7)

    def test_incomplete_phase3_cannot_reach_component(self):
        raw,probe=self.reports();struct.pack_into('<I',raw,516,0)
        with self.assertRaisesRegex(ValueError,'System123 must return'):C.decode(raw,probe,0,{'rows':[]})

    def test_later_context_and_latest_main_must_match(self):
        raw,probe=self.reports();struct.pack_into('<I',probe,20,23)
        with self.assertRaisesRegex(ValueError,'latest original main capture'):C.decode(raw,probe,0,{'rows':[]})

    def test_BufferedImage_side_effect_is_not_ignored(self):
        raw,probe=self.reports();struct.pack_into('<I',probe,12,2)
        with self.assertRaisesRegex(ValueError,'BufferedImage initialized'):C.decode(raw,probe,0,{'rows':[]})

    def test_original_worker_and_native_owner_cleanup_remain_required(self):
        raw,probe=self.reports()
        for at,value in ((136,2),(168,2),(232,1),(452,0),(464,1),(488,1)):
            modified=bytearray(raw);struct.pack_into('<I',modified,at,value)
            with self.subTest(at=at),self.assertRaises(ValueError):C.decode(modified,probe,0,{'rows':[]})
        struct.pack_into('<Q',probe,48,1)
        with self.assertRaisesRegex(ValueError,'active StackWalker generation'):C.decode(raw,probe,0,{'rows':[]})


if __name__=='__main__':unittest.main()
