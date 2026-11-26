"""Game-entry model/real-COFF contracts; does not execute Minecraft Main."""
import copy
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile
import types
import unittest


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('game_main_model',ROOT/'scripts/vm-game-entry.py')
G=importlib.util.module_from_spec(spec);spec.loader.exec_module(G)


def check(value,message):
    if not value:raise ValueError(message)


SIMPLE=types.SimpleNamespace(check=check)


class GameArguments(unittest.TestCase):
    def test_help_scope_and_argument_origin_are_explicit(self):
        m=G.arguments_model(['--help'],SIMPLE)
        self.assertEqual(m['mode'],'server_help');self.assertFalse(m['original_JDK_or_game_input'])
        self.assertEqual(m['argc'],1);self.assertFalse(m['EULA_written_by_bridge'])

    def test_UTF16_empty_surrogates_and_assembly_metacharacters_are_exact(self):
        texts=['','\u03bb\U0001f603','\ud800','"\nEND\nINCLUDE secrets']
        m=G.arguments_model(texts,SIMPLE);assembly=G.data({'argv':m})
        self.assertEqual(m['rows'][1]['utf16'],[0x3bb,0xd83d,0xde03])
        self.assertEqual(m['rows'][2]['utf16'],[0xd800]);self.assertIn(' WORD 0\n',assembly)
        self.assertNotIn('INCLUDE secrets',assembly);self.assertNotIn('\nEND\n',assembly)

    def test_zero_args_still_has_a_valid_data_label(self):
        m=G.arguments_model([],SIMPLE);assembly=G.data({'argv':m})
        self.assertEqual(m['argc'],0);self.assertIn(G.ARGUMENT_ROWS+' LABEL BYTE\n QWORD 0\n DWORD 0,0\n',assembly)

    def test_argument_count_and_UTF16_bounds(self):
        G.arguments_model(['']*64,SIMPLE)
        with self.assertRaisesRegex(ValueError,'Bounded'):G.arguments_model(['']*65,SIMPLE)
        with self.assertRaisesRegex(ValueError,'UTF16 budget'):G.arguments_model(['\U0001f603'*32768],SIMPLE)
        with self.assertRaisesRegex(ValueError,'UTF16 budget'):G.arguments_model(['a'*32768,'b'*32768],SIMPLE)

    def test_credentials_are_rejected(self):
        for value in ('--accessToken=secret','--password','--session-id=secret','--authorization=secret'):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'Credentials'):G.arguments_model([value],SIMPLE)

    def test_resealed_argument_count_UTF16_and_symbol_mutations_rejected(self):
        m={'argv':G.arguments_model(['--help'],SIMPLE)}
        for case in ('count','units','symbol','UTF16','total'):
            other=copy.deepcopy(m)
            if case=='count':other['argv']['argc']=2
            elif case=='units':other['argv']['rows'][0]['units']+=1
            elif case=='symbol':other['argv']['rows'][0]['symbol']='boom_bad\nEND'
            elif case=='UTF16':other['argv']['rows'][0]['utf16'][0]=0
            else:other['argv']['total_utf16_units']+=1
            with self.subTest(case=case),self.assertRaises(ValueError):G.data(other)

    def test_source_ASM_order_preserves_logger_init_and_pending_Context(self):
        text=(ROOT/'native/entry/game_main.asm.inc').read_text()
        stages=['cmp DWORD PTR [rbx],0','cmp DWORD PTR [VM_LEVEL_CELL],4','call boom_java_property_array',
            'mov QWORD PTR [GAME_ARGV_ROOT],rax','call boom_java_property_copy','call boom_class_ensure32',
            'mov DWORD PTR [rsi+544],1','mov DWORD PTR [rsi+548],1','call ORIGINAL_GAME_MAIN','mov DWORD PTR [rsi+552],1']
        positions=[text.index(s) for s in stages];self.assertEqual(positions,sorted(positions))
        self.assertEqual(set(re.findall(r'(?m)^ call (\w+)$',text)),G.CALLBACKS|{'ORIGINAL_GAME_MAIN'})
        self.assertNotRegex(text,r'(?m)^ mov (?:QWORD|DWORD) PTR \[rbx\+(?:16|24)\],')
        self.assertNotRegex(text,r'(?m)^ mov (?:QWORD|DWORD) PTR \[VM_LEVEL_CELL\],')

    def test_real_ML64_COFF_symbols_data_and_unwind(self):
        assembler=Path('D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe')
        if not assembler.is_file():self.skipTest('Pinned development ML64 is not installed')
        sp=importlib.util.spec_from_file_location('game_coff_reader',ROOT/'scripts/parallel-diagnostic-assembly-candidate.py')
        P=importlib.util.module_from_spec(sp);sp.loader.exec_module(P)
        with tempfile.TemporaryDirectory(dir=ROOT/'.boom',prefix='game-entry-coff-') as directory:
            directory=Path(directory).resolve();self.assertTrue(directory.is_relative_to(ROOT/'.boom'))
            text='option casemap:none\n'+''.join(f'EXTERN {n}:PROC\n' for n in sorted(G.CALLBACKS|{'boom_test_original_main'}))
            text+=''.join(f'EXTERN {n}:BYTE\n' for n in ('boom_java_platform_properties_pool','boom_test_main_class','boom_test_roots','boom_test_VM_level'))
            text+='ORIGINAL_GAME_MAIN TEXTEQU <boom_test_original_main>\nGAME_MAIN_CLASS TEXTEQU <boom_test_main_class>\n'
            text+='GAME_ARGC EQU 1\nGAME_ARGV_TEXT_ROWS TEXTEQU <'+G.ARGUMENT_ROWS+'>\nGAME_ARGV_ROOT TEXTEQU <boom_test_roots+40>\nVM_LEVEL_CELL TEXTEQU <boom_test_VM_level>\n'
            text+=G.data({'argv':G.arguments_model(['--help'],SIMPLE)})+(ROOT/'native/entry/game_main.asm.inc').read_text()+'\nEND\n'
            source=directory/'test.asm';obj=directory/'test.obj';source.write_text(text)
            result=subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),source],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout.decode(errors='replace'));coff=P.Coff(obj)
            self.assertEqual(set(coff.functions),{G.HELPER});self.assertEqual(set(P.unwind(coff)),{G.HELPER})
            exports={n for n,s in coff.symbols.items() if s['section']>0 and s['storage']==2};self.assertEqual(exports,{G.ARGUMENT_ROWS})
            row=coff.symbols[G.ARGUMENT_ROWS];section=coff.by_section[row['section']]
            self.assertEqual(int.from_bytes(section['raw'][row['value']+8:row['value']+12],'little'),6)
            textrow=coff.symbols['boom_game_argv_text_0'];raw=coff.by_section[textrow['section']]['raw']
            self.assertEqual(raw[textrow['value']:textrow['value']+12],'--help'.encode('utf-16-le'))


class OriginalMainBinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        summary=ROOT/'.boom/named-module-batches/v148-jdwp-production-b/summary.json'
        plan=ROOT/'.boom/translation-plans/server-v85-2a52b09a09944122baae25b0ddbd4e99'
        if not summary.is_file():raise unittest.SkipTest('Pinned original vanilla batch is not installed')
        sp=importlib.util.spec_from_file_location('main_source_inputs',ROOT/'scripts/runtime-provider-source.py')
        cls.S=importlib.util.module_from_spec(sp);sp.loader.exec_module(cls.S)
        cls.R=cls.S.module('main_source_Code','verify-batch-frames.py');cls.summary=json.loads(summary.read_bytes())
        with (plan/'classes.jsonl').open(encoding='utf-8') as stream:
            cls.owner=next(c for line in stream if (c:=json.loads(line))['name']==G.OWNER and c['origin']['loader']==G.LOADER)
        cls.model=G.contract(cls.summary,cls.owner,cls.S,cls.R)

    def closure(self):
        model=self.model
        return dict(selected_methods={str(m['method']):dict(class_id=m['class_id'],name=m['name'],descriptor=m['descriptor'],
            code_sha256=m['code_sha256'],source_sha256=m['class_sha256']) for m in (model['main'],model['initializer'])},
            selected_classes=[dict(class_id=self.owner['id'],source_sha256=self.owner['origin']['sha256'])],
            objects=[u['object']['path'] for u in model['properties_units']])

    def test_locked_Main_Code_logger_initializer_and_real_String_array(self):
        m=self.model;self.assertFalse(m['selected']);self.assertEqual(m['main']['access'],9)
        self.assertEqual(m['initializer']['access'],8);self.assertTrue(m['original_logger_initializer_preserved'])
        self.assertEqual(m['report_bytes'],576);self.assertEqual(m['report_abi'],14)
        self.assertEqual(m['owner']['origin']['source_id'],self.owner['origin']['source_id']);self.assertFalse(m['host_writes_Java_argv'])

    def test_exact_selected_Code_contract_not_native_execution(self):
        self.assertTrue(G.bind(self.closure(),self.summary,self.owner,self.S,self.R)['selected'])

    def test_unselected_main_or_logger_clinit_is_rejected(self):
        for key in ('main','initializer'):
            closure=self.closure();del closure['selected_methods'][str(self.model[key]['method'])]
            with self.subTest(method=key),self.assertRaisesRegex(ValueError,'must both be selected'):G.bind(closure,self.summary,self.owner,self.S,self.R)

    def test_resealed_wrong_Code_or_class_identity_is_rejected(self):
        for field in ('code_sha256','source_sha256','class_id','descriptor'):
            closure=self.closure();row=closure['selected_methods'][str(self.model['main']['method'])]
            row[field]=0 if field=='class_id' else 'altered'
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'must both be selected'):G.bind(closure,self.summary,self.owner,self.S,self.R)

    def test_missing_actual_properties_COFF_is_rejected(self):
        closure=self.closure();closure['objects']=[]
        with self.assertRaisesRegex(ValueError,'Actual normal properties COFF'):G.bind(closure,self.summary,self.owner,self.S,self.R)

    def test_wrong_original_loader_source_major_or_generated_origin_rejected(self):
        for field,value in (('loader','bootstrap'),('source_id','jdk:java.base'),('java_class_major',64),('generated',{'fake':True})):
            owner=copy.deepcopy(self.owner);owner['origin'][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'original locked'):G.contract(self.summary,owner,self.S,self.R)


if __name__=='__main__':unittest.main()
