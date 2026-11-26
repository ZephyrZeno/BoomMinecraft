"""Protocol fixtures and sealed historical reports; no simulated guest run."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('native_report_protocol',ROOT/'scripts/decode-vm-entry-report.py')
D=importlib.util.module_from_spec(spec);spec.loader.exec_module(D)
FS=dict(file_class=626,field=dict(offset=8))
DIAGNOSTICS=dict(rows=[dict(id=17,category=5,symbol='boom_m100'),dict(id=23,category=1,symbol='boom_m200')])


def put(raw,offset,value,width=4):struct.pack_into('<Q' if width==8 else '<I',raw,offset,value)


def fixture(length=448,owners=False,phase3=False,game=False):
    if game:phase3=True
    model={};manifest=dict(binding_model=model,start_child=False,construct_child=False,signal_control=length>=272,
        include_System_phase1=length>=312,system_phase2=length>=312,system_phase3=phase3)
    if length>=312:model['system_phase2']={'source':'protocol-fixture'}
    if length>=320:model['phase2_context_rows']=True
    if length>=384:model['reference_processing']={'source':'protocol-fixture'}
    if length>=400:model['winnt_filesystem']={'source':'protocol-fixture'}
    if length>=448:model['object_wait']={'source':'protocol-fixture'}
    if owners:model.update(provider_native_root_spans=[dict(symbol='boom_test_roots',count=1,kind='oop')],unsafe_park={'source':'protocol-fixture'},file_input={'source':'protocol-fixture'})
    if phase3:model['system_phase3']={'source':'protocol-fixture'}
    if game:
        manifest['server_help']=True
        model['game_entry']={'argv':{'argc':1,'rows':[dict(index=0,text='--help',units=6,utf16=[45,45,104,101,108,112])]}}
    actual,abi=D.report_layout(manifest);assert actual==length
    manifest.update(execution_report_bytes=length,execution_report_abi=abi);raw=bytearray(length)
    for offset,value in ((0,D.MAGIC),(4,abi),(52,2),(64,7),(72,1),(76,int(length>=312))):put(raw,offset,value)
    if length>=272:
        for offset in (144,148):put(raw,offset,1)
        for offset in (152,168,176):put(raw,offset,1,8)
        for offset in (120,128,216,224,232):put(raw,offset,2,8)
    if length>=312:
        for offset,value in ((272,1),(276,1),(280,1),(288,1),(292,2)):put(raw,offset,value)
    if length>=384:
        for offset in (320,324,328):put(raw,offset,1)
        put(raw,380,6)
    if length>=400:
        for offset,value in ((384,2),(388,1),(396,FS['file_class'])):put(raw,offset,value)
    if length>=448:
        for offset in (400,404,408):put(raw,offset,1)
    if owners:
        for offset in (448,452):put(raw,offset,1)
        put(raw,504,37,8)
    if phase3:
        for offset,value in ((512,1),(516,1),(520,2),(524,4)):put(raw,offset,value)
    if game:
        for offset in (544,548,552,556):put(raw,offset,1)
    return manifest,raw


def decoded(m,raw,exit_code=0,observe=False):
    return D.decode(bytes(raw),m,exit_code,DIAGNOSTICS,filesystem_metadata=FS,observe_source_admissions=observe)


def source_stop(m,raw,phase3=False):
    for offset,value in ((12,D.SOURCE_STOP),(28,2),(32,17),(72,0),(80,86),(296,D.SOURCE_STOP),(300,7),(304,200),(312,23)):
        put(raw,offset,value)
    if phase3:
        put(raw,516,0);put(raw,524,3)
        for offset,value in ((528,D.SOURCE_STOP),(532,7),(536,200)):put(raw,offset,value)
    else:put(raw,280,0);put(raw,292,1)


def game_failure(raw,kind=D.SOURCE_STOP,main_called=False):
    for offset,value in ((12,kind),(72,0),(80,86 if kind==D.SOURCE_STOP else 70),(296,kind),(300,7),(304,200),
        (544,int(main_called)),(548,int(main_called)),(552,0),(560,kind),(564,7),(568,200)):
        put(raw,offset,value)
    if kind==D.SOURCE_STOP:
        for offset,value in ((28,2),(32,17),(312,23)):put(raw,offset,value)


class NativeReportProtocol(unittest.TestCase):
    def test_exact_layout_matrix(self):
        for length,owners,phase3 in [(112,False,False),(272,False,False),(312,False,False),(320,False,False),
            (384,False,False),(400,False,False),(448,False,False),(512,True,False),(544,False,True),(544,True,True)]:
            with self.subTest(length=length,owners=owners):
                manifest,raw=fixture(length,owners,phase3);self.assertTrue(decoded(manifest,raw)['completed_requested_prefix'])

    def test_all_truncated_or_overlong_forms_are_rejected(self):
        for length,owners,phase3 in [(448,False,False),(512,True,False),(544,True,True)]:
            m,raw=fixture(length,owners,phase3)
            for broken in (raw[:-1],raw[:448],raw+b'\0'):
                if len(broken)==length:continue
                with self.subTest(length=length,size=len(broken)),self.assertRaisesRegex(ValueError,'ABI differs'):decoded(m,broken)

    def test_manifest_layout_cannot_override_model(self):
        m,raw=fixture(544,False,True);m.update(execution_report_bytes=512,execution_report_abi=12)
        with self.assertRaisesRegex(ValueError,'Sealed execution report layout'):decoded(m,raw)

    def test_wrong_ABI_with_correct_length_rejected(self):
        m,raw=fixture(544,False,True);put(raw,4,12)
        with self.assertRaisesRegex(ValueError,'ABI differs'):decoded(m,raw)

    def test_phase3_fault_does_not_erase_completed_phase2(self):
        m,raw=fixture(544,False,True);source_stop(m,raw,True);result=decoded(m,raw,86,True)
        self.assertTrue(result['main_System_phases']['phase2_returned']);self.assertEqual(result['main_System_phases']['VM_level_after'],2)
        self.assertFalse(result['completed_requested_prefix']);self.assertFalse(result['System_phase3']['returned'])
        self.assertEqual(result['first_process_fault']['id'],17);self.assertEqual(result['fault']['id'],23)
        self.assertEqual(result['fault_source'],'main_thread');self.assertEqual(result['source_admission_rows'],[23,17])

    def test_phase3_entry_flag_requires_complete_final_outcome(self):
        for offset,value in ((516,0),(520,1),(524,3),(540,1)):
            m,raw=fixture(544,False,True);put(raw,offset,value)
            with self.subTest(offset=offset),self.assertRaises(ValueError):decoded(m,raw)

    def test_phase3_return_with_exception_is_rejected(self):
        m,raw=fixture(544,False,True);put(raw,528,16);put(raw,296,16)
        with self.assertRaisesRegex(ValueError,'Phase3 return'):decoded(m,raw)

    def test_phase3_main_Context_must_match_latest_capture(self):
        m,raw=fixture(544,False,True);source_stop(m,raw,True);put(raw,536,201)
        with self.assertRaisesRegex(ValueError,'Phase3 Context differs'):decoded(m,raw,86)

    def test_phase3_call_cannot_precede_successful_phase2(self):
        m,raw=fixture(544,False,True);put(raw,280,0)
        with self.assertRaisesRegex(ValueError,'Phase3 call requires'):decoded(m,raw)

    def test_phase3_can_report_typed_Java_failure_without_claiming_success(self):
        m,raw=fixture(544,False,True)
        for offset,value in ((12,16),(72,0),(80,70),(296,16),(516,0),(524,3),(528,16)):put(raw,offset,value)
        result=decoded(m,raw,70);self.assertFalse(result['completed_requested_prefix']);self.assertTrue(result['main_System_phases']['phase2_returned'])

    def test_reserved_owner_region_without_metadata_must_be_zero(self):
        for offset,width in ((448,4),(460,4),(472,8),(480,8),(504,8)):
            m,raw=fixture(544,False,True);put(raw,offset,1,width)
            with self.subTest(offset=offset),self.assertRaisesRegex(ValueError,'Absent native owner'):decoded(m,raw)

    def test_snapshot_uncalled_cannot_be_success(self):
        m,raw=fixture(512,True);put(raw,460,0xffffffff);put(raw,504,0,8)
        with self.assertRaisesRegex(ValueError,'failed without'):decoded(m,raw)

    def test_snapshot_error_is_rejected_even_if_native_status_was_falsely_zero(self):
        m,raw=fixture(512,True);put(raw,460,122)
        with self.assertRaisesRegex(ValueError,'Native root snapshot failed'):decoded(m,raw)

    def test_native_snapshot_root_vector_bound(self):
        m,raw=fixture(512,True);put(raw,504,1048577,8)
        with self.assertRaisesRegex(ValueError,'private vector'):decoded(m,raw)

    def test_owner_leaks_are_rejected_not_silently_marked_complete(self):
        for offset,width in ((464,4),(468,4),(472,8),(480,8),(488,8),(496,8)):
            m,raw=fixture(512,True);put(raw,offset,1,width)
            with self.subTest(offset=offset),self.assertRaisesRegex(ValueError,'retains'):decoded(m,raw)

    def test_owner_failure_and_unclosed_Parker_rejected(self):
        for offset,value in ((456,5),(448,2),(452,0)):
            m,raw=fixture(512,True);put(raw,offset,value)
            with self.subTest(offset=offset),self.assertRaises(ValueError):decoded(m,raw)

    def test_source_stop_before_Parker_open_is_observed_but_not_completed(self):
        m,raw=fixture(512,True);source_stop(m,raw);put(raw,448,0);put(raw,452,0)
        result=decoded(m,raw,86);self.assertFalse(result['completed_requested_prefix']);self.assertEqual(result['native_owner_snapshot']['Park_opened'],0)

    def test_missing_native_metadata_rejects_nonzero_family_fields(self):
        for key,offset,width in (('unsafe_park',448,4),('file_input',480,8)):
            m,raw=fixture(512,True);del m['binding_model'][key]
            if key=='unsafe_park':put(raw,452,0)
            put(raw,offset,1,width)
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'Absent'):decoded(m,raw)

    def test_owner_metadata_requires_declared_root_spans(self):
        m,raw=fixture(512,True);m['binding_model']['provider_native_root_spans']=[]
        with self.assertRaisesRegex(ValueError,'requires selected root spans'):decoded(m,raw)

    def test_general_owner_error_and_protocol_lock_still_rejected(self):
        for offset,value in ((68,170),(48,1)):
            m,raw=fixture(544,True,True);put(raw,offset,value)
            with self.subTest(offset=offset),self.assertRaisesRegex(ValueError,'cleanup/protocol'):decoded(m,raw)

    def test_unknown_first_or_latest_main_source_row_is_rejected(self):
        for offset in (32,312):
            m,raw=fixture(544,False,True);source_stop(m,raw,True);put(raw,offset,777)
            with self.subTest(offset=offset),self.assertRaisesRegex(ValueError,'unknown source row|Unknown main-thread'):decoded(m,raw,86)

    def test_old_phase2_exceptional_return_is_still_rejected(self):
        m,raw=fixture(448);put(raw,296,16)
        with self.assertRaisesRegex(ValueError,'Returned phase2'):decoded(m,raw)

    def test_real_historical_448_report_matches_sealed_execution(self):
        directory=ROOT/'.boom/vm-entry-images/2633904e0603469da1cb462e3a24fed1'
        if not (directory/'execution.json').is_file():self.skipTest('Historical native448 artifact is not installed in this checkout')
        manifest=json.loads((directory/'vm-entry.json').read_bytes());old=json.loads((directory/'execution.json').read_bytes())
        raw=(directory/'vm-entry-status.bin').read_bytes();self.assertEqual(len(raw),448)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),old['native_report_sha256'])
        diagnostics=json.loads((Path(manifest['baseline_directory'])/'diagnostic.json').read_bytes())
        filesystem=json.loads(Path(manifest['binding_model']['winnt_filesystem']['metadata']['path']).read_bytes())
        result=D.decode(raw,manifest,old['native_process_exit_code'],diagnostics,filesystem_metadata=filesystem,
            source_verification_sha256=old['source_verification_sha256'],observe_source_admissions='source_admission_rows' in old)
        for key,value in old.items():
            with self.subTest(field=key):self.assertEqual(result.get(key),value)

    def test_CLI_never_overwrites_existing_observation_or_report(self):
        with tempfile.TemporaryDirectory(prefix='report-protocol-',dir=ROOT/'.boom') as directory:
            directory=Path(directory).resolve();self.assertTrue(directory.is_relative_to(ROOT/'.boom'))
            output=directory/'execution.json';output.write_bytes(b'original immutable observation\n')
            report=directory/'vm-entry-status.bin';report.write_bytes(b'protocol fixture, not native execution')
            before=report.read_bytes();original=output.read_bytes()
            argv=['decode-vm-entry-report.py','--manifest',str(directory/'vm-entry.json'),'--report',str(report),
                '--exit-code','0','--accepted-verification-sha256','0'*64,'--output',str(output)]
            with patch.object(sys,'argv',argv),self.assertRaisesRegex(ValueError,'Fresh project report decode'):
                D.main()
            self.assertEqual(report.read_bytes(),before);self.assertEqual(output.read_bytes(),original)

    def test_real_544_Phase3_readonly_replay_without_new_decoder_pin_claim(self):
        directory=ROOT/'.boom/vm-entry-images/v149-phase3-first-a'
        observation=directory/'raw-execution-observation.json'
        if not observation.is_file():self.skipTest('Historical native544 observation is not installed in this checkout')
        old=json.loads(observation.read_bytes());self.assertFalse(old['formal_decoder_verified'])
        for key in ('manifest','native_report','source_native_proof'):D.checked(old[key])
        manifest=json.loads(Path(old['manifest']['path']).read_bytes());raw=Path(old['native_report']['path']).read_bytes()
        self.assertEqual(len(raw),544)
        self.assertNotIn(str((ROOT/'scripts/decode-vm-entry-report.py').resolve()),[str(Path(r['path']).resolve()) for r in manifest['inputs']])
        diagnostics=json.loads((Path(manifest['baseline_directory'])/'diagnostic.json').read_bytes())
        filesystem=json.loads(Path(manifest['binding_model']['winnt_filesystem']['metadata']['path']).read_bytes())
        decoded=D.decode(raw,manifest,old['native_process_exit_code'],diagnostics,filesystem_metadata=filesystem,
            source_verification_sha256=old['source_native_proof']['digest']['sha256'])
        self.assertTrue(decoded['completed_requested_prefix']);self.assertTrue(decoded['main_System_phases']['phase2_returned'])
        third=decoded['System_phase3'];self.assertTrue(third['called'] and third['returned'] and third['completed'])
        self.assertEqual((third['VM_level_before'],third['VM_level_after']),(2,4))
        self.assertEqual([third[k] for k in ('kind','pc','method','depth')],old['phase3_Context'])
        self.assertEqual(decoded['worker_failure_state'],0);self.assertEqual(decoded['cleanup_flags'],7)
        self.assertIsNone(decoded['fault']);self.assertNotIn('native_owner_snapshot',decoded)
        self.assertEqual(json.loads(observation.read_bytes()),old)

    def test_Game576_help_return_is_not_full_game_or_world_success(self):
        m,raw=fixture(576,game=True);result=decoded(m,raw)
        self.assertTrue(result['completed_requested_prefix']);self.assertTrue(result['server_help_completed'])
        self.assertTrue(result['game_entry']['main_called']);self.assertTrue(result['game_entry']['main_returned'])
        self.assertEqual(result['game_entry']['arguments'],['--help']);self.assertEqual(result['execution_report_abi'],14)
        for flag in ('game_started','world_created','full_VM_bootstrap'):self.assertIs(result[flag],False)

    def test_Game576_normal_Context_can_differ_from_prior_Phase3_Context(self):
        m,raw=fixture(576,game=True)
        for offset,value in ((300,19),(304,222),(564,19),(568,222),(532,419),(536,43962)):put(raw,offset,value)
        result=decoded(m,raw);self.assertTrue(result['System_phase3']['completed']);self.assertTrue(result['game_entry']['completed'])
        self.assertNotEqual(result['System_phase3']['method'],result['game_entry']['method'])

    def test_Game576_logger_initializer_source_stop_preserves_Phase3_success(self):
        m,raw=fixture(576,game=True);game_failure(raw)
        result=decoded(m,raw,86,True)
        self.assertTrue(result['System_phase3']['completed']);self.assertTrue(result['main_System_phases']['phase2_returned'])
        self.assertFalse(result['game_entry']['class_initialized']);self.assertFalse(result['game_entry']['main_called'])
        self.assertEqual(result['game_entry']['argc'],1);self.assertFalse(result['completed_requested_prefix'])
        self.assertEqual(result['fault']['id'],23);self.assertEqual(result['first_process_fault']['id'],17)
        self.assertEqual(result['source_admission_rows'],[23,17]);self.assertEqual(result['fault_source'],'main_thread')

    def test_Game576_argv_or_ClassInit_failure_exit70_is_a_failed_prefix(self):
        for kind in (3,8,16):
            m,raw=fixture(576,game=True);game_failure(raw,kind)
            with self.subTest(kind=kind):
                result=decoded(m,raw,70);self.assertTrue(result['System_phase3']['completed'])
                self.assertFalse(result['game_entry']['main_called']);self.assertEqual(result['game_entry']['kind'],kind)
                self.assertFalse(result['completed_requested_prefix'])

    def test_Game576_actual_Main_exception_and_source_stop_are_not_completion(self):
        for kind in (16,D.SOURCE_STOP):
            m,raw=fixture(576,game=True);game_failure(raw,kind,True)
            with self.subTest(kind=kind):
                result=decoded(m,raw,86 if kind==D.SOURCE_STOP else 70)
                self.assertTrue(result['game_entry']['main_called']);self.assertFalse(result['game_entry']['main_returned'])
                self.assertFalse(result['completed_requested_prefix']);self.assertTrue(result['System_phase3']['completed'])

    def test_Game576_Phase3_failure_leaves_entire_Game_region_zero(self):
        m,raw=fixture(576,game=True);source_stop(m,raw,True);raw[544:576]=bytes(32)
        result=decoded(m,raw,86);self.assertFalse(result['System_phase3']['completed']);self.assertEqual(result['game_entry']['argc'],0)
        for offset in range(544,576,4):
            broken=bytearray(raw);put(broken,offset,1)
            with self.subTest(offset=offset),self.assertRaises(ValueError):decoded(m,broken,86)

    def test_Game576_cannot_skip_any_original_System_phase(self):
        for key in ('system_phase2','system_phase3','include_System_phase1'):
            m,raw=fixture(576,game=True);m[key]=False
            with self.subTest(key=key),self.assertRaises(ValueError):decoded(m,raw)

    def test_Game576_model_and_request_flags_must_agree(self):
        m,raw=fixture(576,game=True);m['server_help']=False
        with self.assertRaisesRegex(ValueError,'Game entry request differs'):decoded(m,raw)
        m,raw=fixture(576,game=True);del m['binding_model']['game_entry']
        with self.assertRaisesRegex(ValueError,'Game entry request differs'):decoded(m,raw)

    def test_Game576_own_ABI_and_exact_length_required(self):
        m,raw=fixture(576,game=True)
        for broken in (raw[:-1],raw[:544],raw+bytes(1)):
            with self.subTest(size=len(broken)),self.assertRaisesRegex(ValueError,'ABI differs'):decoded(m,broken)
        put(raw,4,13)
        with self.assertRaisesRegex(ValueError,'ABI differs'):decoded(m,raw)

    def test_Game576_report_argc_must_match_explicit_argument_length(self):
        for count in (0,2,0xffffffff):
            m,raw=fixture(576,game=True);put(raw,556,count)
            with self.subTest(count=count),self.assertRaisesRegex(ValueError,'Game report argc'):decoded(m,raw)

    def test_Game576_model_argv_count_and_text_representations_must_agree(self):
        m,raw=fixture(576,game=True);m['binding_model']['game_entry']['argv']['argc']=2
        with self.assertRaisesRegex(ValueError,'Source Game argc'):decoded(m,raw)
        m,raw=fixture(576,game=True);m['binding_model']['game_entry']['arguments']=['nogui']
        with self.assertRaisesRegex(ValueError,'representations differ'):decoded(m,raw)
        m,raw=fixture(576,game=True);m['binding_model']['game_entry']['argv']['rows'][0]['text']='nogui'
        with self.assertRaisesRegex(ValueError,'ServerHelp must bind exactly'):decoded(m,raw)

    def test_Game576_explicit_arguments_field_supported_without_rows(self):
        m,raw=fixture(576,game=True);m['binding_model']['game_entry']={'arguments':['--help']}
        self.assertTrue(decoded(m,raw)['game_entry']['main_returned'])

    def test_Game576_three_new_flags_are_strict_booleans(self):
        for offset in (544,548,552):
            m,raw=fixture(576,game=True);put(raw,offset,2)
            with self.subTest(offset=offset),self.assertRaisesRegex(ValueError,'Invalid boolean Game'):decoded(m,raw)

    def test_Game576_class_call_and_return_order_is_strict(self):
        for offset in (544,548):
            m,raw=fixture(576,game=True);put(raw,offset,0)
            with self.subTest(offset=offset),self.assertRaisesRegex(ValueError,'Game Main'):decoded(m,raw)

    def test_Game576_false_normal_or_live_return_Context_rejected(self):
        for offset,value in ((560,16),(572,1)):
            m,raw=fixture(576,game=True);put(raw,offset,value);put(raw,296 if offset==560 else 308,value)
            with self.subTest(offset=offset),self.assertRaisesRegex(ValueError,'exceptional or live Context'):decoded(m,raw)
        m,raw=fixture(576,game=True);put(raw,552,0)
        with self.assertRaisesRegex(ValueError,'Normal Game Main call'):decoded(m,raw)

    def test_Game576_no_call_requires_real_argv_or_initializer_failure_Context(self):
        m,raw=fixture(576,game=True)
        for offset in (544,548,552):put(raw,offset,0)
        put(raw,72,0);put(raw,80,70)
        with self.assertRaisesRegex(ValueError,'Uncalled Game Main has no'):decoded(m,raw,70)

    def test_Game576_latest_main_must_match_Game_Context(self):
        m,raw=fixture(576,game=True);game_failure(raw);put(raw,568,201)
        with self.assertRaisesRegex(ValueError,'Game Context differs'):decoded(m,raw,86)

    def test_Game576_entry72_follows_final_Game_not_earlier_Phase3_success(self):
        m,raw=fixture(576,game=True);game_failure(raw);put(raw,72,1)
        with self.assertRaisesRegex(ValueError,'Main-thread return differs'):decoded(m,raw,86)
        m,raw=fixture(576,game=True);put(raw,72,0);put(raw,80,70)
        with self.assertRaisesRegex(ValueError,'Main-thread return differs'):decoded(m,raw,70)

    def test_Game576_source_stop_without_source_record_cannot_be_exit70_exception(self):
        m,raw=fixture(576,game=True);game_failure(raw);put(raw,28,0);put(raw,32,0);put(raw,312,0);put(raw,80,70)
        with self.assertRaisesRegex(ValueError,'failed without'):decoded(m,raw,70)

    def test_Game576_owner_failure_and_busy_state_remain_rejected(self):
        for offset,value in ((68,170),(464,1),(480,1)):
            m,raw=fixture(576,owners=True,game=True);put(raw,offset,value)
            with self.subTest(offset=offset),self.assertRaises(ValueError):decoded(m,raw)


if __name__=='__main__':unittest.main()
