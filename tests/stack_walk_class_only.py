"""Original StackWalker constants and real canonical-machine COFF boundaries."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest


ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location('stack_walk_test_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

B=module('stack-walk-candidate');C,S=B.C,B.S
BASE=ROOT/'.boom/stack-walk/source-v150-b'
PINS=ROOT/'.boom/stack-walk/pinned-sources/jdk-21.0.13+3'


@unittest.skipUnless((BASE/'candidate.json').is_file(),'Requires the independent current StackWalker candidate fixture')
class StackWalkSourceAndMachine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate=S.read(BASE/'candidate.json');cls.meta=cls.candidate['metadata']['source']
        summary=S.read(Path(cls.candidate['metadata']['base']['batch'])/'summary.json')
        plan=Path(cls.candidate['metadata']['base']['plan'])
        I=S.module('stack_walk_boundary_class_parser','verify-translation-ir.py');cls.I=I
        wanted={C.OWNER,C.BUFFER};owners={}
        with (plan/'classes.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                row=B.json.loads(line)
                if row['name'] in wanted and row['origin']['loader']=='bootstrap':owners[row['name']]=row
        cls.raw=I.Source(S.original_class(summary,owners[C.OWNER]));cls.buffer=I.Source(S.original_class(summary,owners[C.BUFFER]))
        parent=ROOT/'.boom/stack-walk/boundary-tests';parent.mkdir(exist_ok=True)
        cls.temporary=tempfile.TemporaryDirectory(dir=parent);cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory=Path(cls.temporary.name)

    def test_actual_classfile_Java_native_modes_and_reserved_slots_agree(self):
        protocol=C.protocol(self.raw,self.buffer,{n:PINS/n for n in C.PINS},S)
        self.assertEqual(protocol['modes'],{'FILL_CLASS_REFS_ONLY':2,'GET_CALLER_CLASS':4,'SHOW_HIDDEN_FRAMES':32,'FILL_LIVE_STACK_FRAMES':256})
        self.assertEqual((protocol['START_POS'],protocol['magic_pos']),(2,0))
        self.assertEqual(protocol['callback_descriptor'],'(JIIII)Ljava/lang/Object;')

    def test_mismatched_native_mode_is_rejected_before_codegen(self):
        paths={n:PINS/n for n in C.PINS};replacement=self.directory/'jvm.h'
        replacement.write_text(paths['jvm.h'].read_text().replace('JVM_STACKWALK_GET_CALLER_CLASS           = 0x04','JVM_STACKWALK_GET_CALLER_CLASS           = 0x08'))
        paths['jvm.h']=replacement
        with self.assertRaisesRegex(ValueError,'constant mismatch'):C.protocol(self.raw,self.buffer,paths,S)

    def test_resealed_classfile_constant_is_not_trusted(self):
        raw=deepcopy(self.raw)
        [index]=[f['constant_value'] for f in raw.fields if f['name']=='FILL_CLASS_REFS_ONLY']
        raw.cp[index]=(3,(8).to_bytes(4,'big'))
        with self.assertRaisesRegex(ValueError,'constant mismatch'):C.protocol(raw,self.buffer,{n:PINS/n for n in C.PINS},S)

    def test_magic_is_not_confused_with_both_reserved_slots(self):
        paths={n:PINS/n for n in C.PINS};replacement=self.directory/'stackwalk.hpp'
        replacement.write_text(paths['stackwalk.hpp'].read_text().replace('magic_pos = 0','magic_pos = 1'))
        paths['stackwalk.hpp']=replacement
        with self.assertRaisesRegex(ValueError,'reserved buffer/magic'):C.protocol(self.raw,self.buffer,paths,S)

    def test_private_callback_and_inherited_FMAP_are_original_source(self):
        [callback]=[r for r in self.meta['java_callbacks'] if r['name']=='doStackWalk']
        self.assertEqual((callback['access'],callback['descriptor'],callback['code_bytes']),(2,'(JIIII)Ljava/lang/Object;',82))
        fields={r['name']:r for r in self.meta['fields']}
        self.assertEqual(set(fields),{'thread','mode','contScope','continuation'})
        self.assertTrue(all(len(r['field_map']['rows'])==4 for r in fields.values()))
        self.assertGreater(len({r['offset'] for r in fields['mode']['field_map']['rows']}),1)

    def test_original_declarations_have_no_Java_Code_or_execution_claim(self):
        self.assertEqual([(r['name'],r['access']) for r in self.meta['methods']],
                         [('checkStackWalkModes',0x10a),('callStackWalk',0x102),('fetchStackFrames',0x102)])
        self.assertTrue(all('code_sha256' not in r and r['frame_flags']==32 for r in self.meta['methods']))
        proof=S.read(BASE/'verification.json')
        self.assertTrue(proof['canonical_reassembly_all_nondebug_bytes_and_relocations_verified'])
        self.assertFalse(proof['callback_execution_verified']);self.assertFalse(proof['registered'])

    def test_changed_instruction_with_identical_exports_is_rejected(self):
        data=bytearray(S.checked(self.candidate['object']).read_bytes())
        for n in range(struct.unpack_from('<H',data,2)[0]):
            at=20+n*40
            if bytes(data[at:at+8]).rstrip(b'\0') in (b'.text',b'.text$mn'):
                raw=struct.unpack_from('<I',data,at+20)[0];data[raw]^=1;break
        else:self.fail('Actual candidate has no text section')
        changed=self.directory/'instruction.obj';changed.write_bytes(data)
        self.assertEqual(B.A.coff_symbols(changed,C.FOREIGN),B.A.coff_symbols(S.checked(self.candidate['object']),C.FOREIGN))
        with self.assertRaisesRegex(ValueError,'instructions/data/relocation'):
            B.machine_contract(S.checked(self.candidate['assembly']).read_text(),changed,Path(self.candidate['assembler']['path']))

    def test_swapped_undefined_symbols_cannot_redirect_same_relocation_indices(self):
        data=bytearray(S.checked(self.candidate['object']).read_bytes())
        table,count=struct.unpack_from('<II',data,8);strings=table+count*18;index=0;found=[]
        while index<count:
            at=table+18*index;name=bytes(data[at:at+8]);_,section,_,storage,aux=struct.unpack_from('<IhHBB',data,at+8)
            if name[:4]==bytes(4):
                start=strings+int.from_bytes(name[4:],'little');text=bytes(data[start:data.index(0,start)]).decode()
            else:text=name.rstrip(b'\0').decode()
            if section==0 and storage==2 and text in ('boom_trace_enter','boom_trace_leave'):found.append((at,name))
            index+=1+aux
        self.assertEqual(len(found),2);(a,left),(b,right)=found;data[a:a+8],data[b:b+8]=right,left
        changed=self.directory/'symbol-swap.obj';changed.write_bytes(data)
        self.assertEqual(B.A.coff_symbols(changed,C.FOREIGN),B.A.coff_symbols(S.checked(self.candidate['object']),C.FOREIGN))
        with self.assertRaisesRegex(ValueError,'instructions/data/relocation'):
            B.machine_contract(S.checked(self.candidate['assembly']).read_text(),changed,Path(self.candidate['assembler']['path']))


if __name__=='__main__':unittest.main()
