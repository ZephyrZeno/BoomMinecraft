"""Only source-bound entry adapters may gain ASM native frames."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('native_frame_adapter_tests',Path(__file__).resolve().parents[1]/'scripts/native-frame-adapters.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


def fixture():
    method=dict(method=12,class_id=4,class_sha256='a'*64,loader='bootstrap',source_id='jdk:java.base',
                owner='java/lang/Example',name='call',descriptor='()V',access=0x109,operation=7)
    manifest=dict(methods=[method],pool_symbol='boom_fixture_pool',service_symbol='boom_fixture_service')
    row={k:v for k,v in method.items() if k not in ('method','owner','operation')}
    row.update(id=12,class_name=method['owner'],flags=32)
    tail='.const\nboom_fixture_pool QWORD 123\n.code\nboom_fixture_service PROC\n ret\nboom_fixture_service ENDP\nEND\n'
    text='option casemap:none\n'+M.V.wrapper(method,manifest['pool_symbol'],manifest['service_symbol'])+tail
    return text,manifest,{12:row},tail


class NativeFrameAdapterTests(unittest.TestCase):
    def test_frames_wrap_exact_native_entry_and_keep_service_metadata_unchanged(self):
        text,m,rows,tail=fixture();out,imports,ids=M.rewrite(text,m,rows)
        self.assertTrue(out.endswith(tail));self.assertEqual(ids,[12])
        self.assertIn('lea r8,boom_trace_method12',out);self.assertIn('call boom_trace_enter',out)
        self.assertIn('call boom_trace_leave',out);self.assertIn('mov r9d,7\n jmp boom_fixture_service',out)
        self.assertIn('boom_trace_method12',imports);self.assertIn('lea r8,boom_fixture_pool',out)
        self.assertIn('PUBLIC boom_m12_native',out)

    def test_missing_unavailable_or_wrong_original_native_rows_are_rejected(self):
        text,m,rows,_=fixture()
        for key,value in [('flags',0),('flags',160),('class_id',5),('name','other')]:
            bad=copy.deepcopy(rows);bad[12][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):M.rewrite(text,m,bad)
        with self.assertRaises(ValueError):M.rewrite(text,m,{})

    def test_replacement_requires_one_exact_original_wrapper(self):
        text,m,rows,_=fixture()
        for bad in [text.replace('sub rsp,56','sub rsp,72'),text+M.V.wrapper(m['methods'][0],m['pool_symbol'],m['service_symbol'])]:
            with self.assertRaisesRegex(ValueError,'exact original wrapper'):M.rewrite(bad,m,rows)


if __name__=='__main__':unittest.main()
