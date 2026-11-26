"""Validate replay guards using the actual sealed ABI11 report and exact RSP edits."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('split_native_prefix_probe',ROOT/'scripts/parallel-diagnostic-native-prefix-probe.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)


class ExactResponsePatch(unittest.TestCase):
    def test_preserves_every_other_response_line_and_order(self):
        old=ROOT/'.boom/original.obj';objects=[ROOT/'.boom/data.obj',ROOT/'.boom/code.obj']
        target=ROOT/'.boom/new/boom-vm-entry.exe'
        raw=('/NODEFAULTLIB\r\n/OUT:"old.exe"\r\n"'+str(old)+'"\r\n"unchanged.lib"\r\n/EXPORT:boom_main\r\n').encode()
        expected=('/NODEFAULTLIB\r\n/OUT:"'+str(target)+'"\r\n'+
                  ''.join('"'+str(p)+'"\r\n' for p in objects)+'"unchanged.lib"\r\n/EXPORT:boom_main\r\n').encode()
        self.assertEqual(P.patch_response(raw,old,objects,target),expected)

    def test_duplicate_closure_replacement_is_rejected(self):
        old=ROOT/'.boom/original.obj'
        raw=('/OUT:"old.exe"\n"'+str(old)+'"\n"'+str(old)+'"\n').encode()
        with self.assertRaisesRegex(ValueError,'exactly one'):P.patch_response(raw,old,[ROOT/'.boom/new.obj'],ROOT/'.boom/new.exe')

    def test_incomplete_response_line_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'complete lines'):
            P.patch_response(b'/OUT:"old.exe"',ROOT/'.boom/original.obj',[],ROOT/'.boom/new.exe')


class SealedNativeReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory=ROOT/'.boom/vm-entry-images/a7c5084275e0419db074936e926fd155'
        if not (directory/'vm-entry-status.bin').is_file():raise unittest.SkipTest('The real sealed v145 native report is required')
        cls.raw=(directory/'vm-entry-status.bin').read_bytes()
        execution=json.loads((directory/'execution.json').read_bytes())
        assert execution['native_report_sha256']==hashlib.sha256(cls.raw).hexdigest()
        cls.baseline=P.report(cls.raw);cls.fault=execution['fault'];cls.exit_code=execution['native_process_exit_code']

    def validate_changed(self,offset,value,width):
        raw=bytearray(self.raw);struct.pack_into('<Q' if width==8 else '<I',raw,offset,value)
        P.validate_prefix(P.report(raw),self.baseline,self.exit_code,self.fault)

    def test_accepts_actual_owned_process_report(self):
        P.validate_prefix(P.report(self.raw),self.baseline,self.exit_code,self.fault)

    def test_short_report_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'448'):P.report(self.raw[:-1])

    def test_wrong_abi_is_rejected(self):
        raw=bytearray(self.raw);struct.pack_into('<I',raw,4,10)
        with self.assertRaisesRegex(ValueError,'ABI11'):P.report(raw)

    def test_missing_phase1_return_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'phase prefix'):self.validate_changed(272,0,4)

    def test_wrong_main_source_row_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'source stop'):self.validate_changed(312,self.baseline['main_source_row']+1,4)

    def test_missing_original_worker_exit_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'lifecycle'):self.validate_changed(128,1,8)

    def test_held_monitor_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'cleanup invariant'):self.validate_changed(40,1,8)

    def test_unclosed_reference_domain_is_rejected(self):
        with self.assertRaises(ValueError):self.validate_changed(328,0,4)

    def test_object_wait_owner_error_is_rejected(self):
        with self.assertRaises(ValueError):self.validate_changed(412,5,4)


if __name__=='__main__':unittest.main()
