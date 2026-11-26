"""Original Phase3 binding and actual AMD64 read-only owner boundaries."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
from types import SimpleNamespace
import unittest
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
STATE=ROOT/'.boom/formal-native-transitions/module-runtime-v148-a/pending-state.json'
CLOSURE=ROOT/'.boom/diagnostic-startup/v148-native-modules-ae1c57ec1bb24f1d812d5dc91d4987d7/round-000/closure.json'
ASSEMBLER=Path('D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe')


def load(name):
    spec=importlib.util.spec_from_file_location('phase3_test_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


S,P,F,A=(load(n) for n in ('runtime-provider-source','vm-system-phase3','verify-batch-frames','verify-batch-assembly'))


@unittest.skipUnless(STATE.is_file() and CLOSURE.is_file(), 'Requires immutable original 29-family source inputs')
class SystemPhase3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        state=S.read(STATE);cls.summary=S.read(Path(state['batch'])/'summary.json')
        classes={}
        with (Path(state['plan'])/'classes.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                c=json.loads(line)
                if c['name'] in ('java/lang/System','jdk/internal/misc/VM') and c['origin']['loader']=='bootstrap':classes[c['name']]=c
        cls.owner=classes['java/lang/System']
        contract=P.contract(cls.summary,cls.owner,S,F)
        closure=S.read(CLOSURE)
        cls.closure=dict(selected_methods={str(contract['method']):closure['selected_methods'][str(contract['method'])]})
        cls.model=P.bind(cls.closure,cls.summary,cls.owner,S,F)
        vm=classes['jdk/internal/misc/VM']
        [level]=[i for i,f in enumerate(vm['fields']) if (f['name'],f['descriptor'])==('initLevel','I') and f['access']&8]
        cls.level=f"boom_s{vm['id']}_{level}"

    def test_binds_actual_original_complete_phase3(self):
        self.assertEqual(self.model['method'],43962)
        self.assertEqual(self.model['code_bytes'],427)
        self.assertEqual(self.model['code_sha256'],'52a98868c6762cbd222e079c0d82e741110d3fc944dfdb5cc9231963466f9efc')
        self.assertEqual([r['value'] for r in self.model['original_VM_level_calls']],[3,4])
        self.assertEqual(self.model['source_exception_handlers'],[dict(start=209,end=325,target=328,catch_type='java/lang/Exception')])
        self.assertIn('java/lang/invoke/StringConcatFactory',self.model['source_initializer_dependencies'])

    def test_rejects_unselected_or_changed_selected_source(self):
        with self.assertRaisesRegex(ValueError,'selected intact'):
            P.bind(dict(selected_methods={}),self.summary,self.owner,S,F)
        for key,value in [('code_sha256','0'*64),('source_sha256','0'*64),('class_id',-1),('descriptor','()I')]:
            changed=deepcopy(self.closure);changed['selected_methods'][str(self.model['method'])][key]=value
            with self.subTest(field=key),self.assertRaisesRegex(ValueError,'selected intact'):
                P.bind(changed,self.summary,self.owner,S,F)

    def test_rejects_generated_or_other_loader_System(self):
        for field,value in [('generated',True),('loader','vanilla-application'),('source_id','other')]:
            owner=deepcopy(self.owner);owner['origin'][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'original final bootstrap System'):
                P.bind(self.closure,self.summary,owner,S,F)

    def test_independent_parser_rejects_forged_code_view(self):
        name,methods=F.original_methods(S.original_class(self.summary,self.owner));methods=deepcopy(methods)
        [method]=[m for m in methods if m['name']=='initPhase3']
        body=bytearray(method['code'][0]);body[0]^=1;method['code']=(bytes(body),*method['code'][1:])
        reader=SimpleNamespace(original_methods=lambda _:(name,methods))
        with self.assertRaisesRegex(ValueError,'Independent original Phase3 Code parsers differ'):
            P.contract(self.summary,self.owner,S,reader)

    def test_report_544_extends_prefix_and_never_claims_java_state_writes(self):
        self.assertEqual((self.model['report_bytes'],self.model['report_abi']),(544,13))
        self.assertEqual(list(self.model['report_fields'].values()),list(range(512,544,4)))
        self.assertEqual((self.model['initial_VM_level'],self.model['success_VM_level']),(2,4))
        self.assertFalse(self.model['ASM_writes_Java_state'])
        self.assertFalse(self.model['ASM_sets_VM_level'])
        self.assertFalse(self.model['full_game_startup_claimed'])

    @unittest.skipUnless(ASSEMBLER.is_file() and importlib.util.find_spec('capstone'), 'Requires local ml64 and Capstone')
    def test_actual_COFF_calls_original_once_and_only_reads_VM_cell(self):
        from capstone import Cs,CS_ARCH_X86,CS_MODE_64,CS_AC_WRITE
        from capstone.x86_const import X86_OP_MEM,X86_REG_RSI,X86_REG_RBX
        output=ROOT/'.boom/system-phase3-tests'/uuid4().hex;output.mkdir(parents=True)
        text=(f'option casemap:none\nEXTERN {self.level}:DWORD\nEXTERN {self.model["symbol"]}:PROC\n'
              f'VM_LEVEL_CELL TEXTEQU <{self.level}>\nORIGINAL_SYSTEM_PHASE3 TEXTEQU <{self.model["symbol"]}>\n')
        text+=(ROOT/'native/entry/system_phase3.asm.inc').read_text(encoding='utf-8')+'\nEND\n'
        asm,obj=output/'phase3.asm',output/'phase3.obj';asm.write_text(text,encoding='utf-8')
        with (output/'assembler.log').open('xb') as log:
            subprocess.run([str(ASSEMBLER),'/nologo','/c','/Fo'+str(obj),str(asm)],stdout=log,stderr=log,check=True)
        self.assertEqual(A.coff_symbols(obj),(set(),{self.level,self.model['symbol']}))
        raw=obj.read_bytes();_,count,_,table,entries,_,_=struct.unpack_from('<HHIIIHH',raw);strings=table+18*entries
        names={};i=0
        while i<entries:
            at=table+i*18;name=raw[at:at+8];aux=raw[at+17]
            if name[:4]==bytes(4):
                start=strings+int.from_bytes(name[4:],'little');name=raw[start:raw.index(0,start)]
            names[i]=name.rstrip(b'\0').decode();i+=1+aux
        [section]=[20+40*i for i in range(count) if raw[20+40*i:28+40*i].rstrip(b'\0').startswith(b'.text')]
        size,pointer,relocation,_,nrel,_,_=struct.unpack_from('<IIIIHHI',raw,section+16)
        cs=Cs(CS_ARCH_X86,CS_MODE_64);cs.detail=True;instructions=list(cs.disasm(raw[pointer:pointer+size],0))
        reads=calls=0;writes=[]
        for at,symbol,kind in struct.iter_unpack('<IIH',raw[relocation:relocation+nrel*10]):
            [instruction]=[op for op in instructions if op.address<=at<op.address+op.size]
            if names[symbol]==self.level:
                self.assertEqual(instruction.mnemonic,'mov')
                self.assertEqual(instruction.operands[1].type,X86_OP_MEM)
                self.assertFalse(instruction.operands[1].access&CS_AC_WRITE);reads+=1
            elif names[symbol]==self.model['symbol']:
                self.assertEqual(instruction.mnemonic,'call');calls+=1
        for instruction in instructions:
            for operand in instruction.operands:
                if operand.type==X86_OP_MEM and operand.access&CS_AC_WRITE:
                    self.assertNotEqual(operand.mem.base,X86_REG_RBX,'Game Context is read-only')
                    if operand.mem.base==X86_REG_RSI:
                        self.assertGreaterEqual(operand.mem.disp,512)
                        self.assertLessEqual(operand.mem.disp+operand.size,544)
                        writes.append(operand.mem.disp)
        self.assertEqual((reads,calls),(2,1))
        self.assertEqual(set(writes),{512,516,520,524,528,536})


if __name__=='__main__':unittest.main()
