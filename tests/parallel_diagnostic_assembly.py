"""Real ml64 fixtures for the isolated COFF equivalence candidate; no guest runtime."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import unittest
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('parallel_assembly_candidate',ROOT/'scripts/parallel-diagnostic-assembly-candidate.py')
P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)
ML64=Path(os.environ.get('BOOM_TEST_ML64','D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe'))
DATA='''
.data?
PUBLIC boom_probe_static_roots
boom_probe_static_roots QWORD 2 DUP(?)
.data
PUBLIC boom_flag
boom_flag DWORD 0
.const
PUBLIC boom_probe_static_root_count
boom_probe_static_root_count QWORD 2
ALIGN 8
PUBLIC boom_double
boom_double QWORD 0
'''
FIRST='''
boom_first PROC FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 cmp DWORD PTR [boom_flag],0
 ucomisd xmm0,QWORD PTR [boom_double]
 call boom_second
 add rsp,40
 ret
boom_first ENDP
'''
SECOND='''
boom_second PROC FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
 mov eax,42
 add rsp,40
 ret
boom_second ENDP
'''


class RealCoffEquivalence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ML64.is_file():raise unittest.SkipTest('A real Windows ml64 assembler is required')
        cls.output=ROOT/'.boom/parallel-diagnostic-assembly-tests'/uuid4().hex
        cls.output.mkdir(parents=True)

    def asm(self,name,text):
        path=self.output/(self.id().split('.')[-1]+'-'+name+'.asm')
        path.write_text('option casemap:none\n'+text+'\nEND\n',encoding='utf-8')
        with path.with_suffix('.log').open('wb') as log:
            r=subprocess.run([str(ML64),'/nologo','/c','/Fo'+str(path.with_suffix('.obj')),str(path)],
                stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.assertEqual(r.returncode,0,path.with_suffix('.log').read_text())
        return path.with_suffix('.obj')

    def normal(self):
        pointer='.data\nPUBLIC boom_pointer\nboom_pointer QWORD OFFSET boom_second\n'
        original=self.asm('original',DATA+pointer+'.code\nPUBLIC boom_first\nPUBLIC boom_second\n'+FIRST+SECOND)
        data=self.asm('data','EXTERN boom_second:PROC\n'+DATA+pointer)
        first=self.asm('first','EXTERN boom_flag:BYTE\nEXTERN boom_double:BYTE\nEXTERN boom_second:PROC\n.code\nPUBLIC boom_first\n'+FIRST)
        second=self.asm('second','.code\nPUBLIC boom_second\n'+SECOND)
        return dict(monolithic_object=P.digest(original),functions={'boom_first':None,'boom_second':None},
                    framed_functions=['boom_first','boom_second'],
                    units=[dict(object=P.digest(p)) for p in (data,first,second)])

    def test_real_resolved_call_rip_relocation_unwind_and_root_layout(self):
        proof=P.equivalence(self.normal())
        self.assertTrue(proof['verified'])
        self.assertEqual(proof['source_procedures'],2)
        self.assertEqual(proof['framed_procedures'],2)
        self.assertEqual(proof['contiguous_static_roots'],dict(section='.bss',offset=0,cells=2,bytes=16))

    def test_machine_instruction_change_fails(self):
        manifest=self.normal()
        changed=self.asm('changed','.code\nPUBLIC boom_second\n'+SECOND.replace('eax,42','eax,43'))
        manifest['units'][2]['object']=P.digest(changed)
        with self.assertRaisesRegex(ValueError,'Machine code'):P.equivalence(manifest)

    def test_real_ucomisd_rip_modrm_requires_four_encoded_displacement_bytes(self):
        import capstone
        decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64);decoder.detail=True
        raw=bytes.fromhex('66 0f 2e 05 00 00 00 00');instruction=next(decoder.disasm(raw,0))
        self.assertEqual(instruction.mnemonic,'ucomisd')
        self.assertEqual(instruction.bytes[instruction.modrm_offset]&0xc7,5)
        self.assertEqual(instruction.disp_offset,instruction.modrm_offset+1)
        self.assertEqual(len(raw)-instruction.disp_offset,4)
        self.assertTrue(P.equivalence(self.normal())['rip_disp32_validated_from_actual_modrm'])

    def test_same_zero_relocation_bytes_with_wrong_target_fails(self):
        manifest=self.normal()
        changed=self.asm('changed-data','EXTERN boom_first:PROC\n'+DATA+
            '.data\nPUBLIC boom_pointer\nboom_pointer QWORD OFFSET boom_first\n')
        manifest['units'][0]['object']=P.digest(changed)
        with self.assertRaisesRegex(ValueError,'Data bytes, relocations'):P.equivalence(manifest)

    def test_moved_contiguous_roots_fail(self):
        manifest=self.normal()
        changed=self.asm('moved-roots','EXTERN boom_second:PROC\n'+DATA.replace('.data?','.data?\n QWORD ?')+
            '.data\nPUBLIC boom_pointer\nboom_pointer QWORD OFFSET boom_second\n')
        manifest['units'][0]['object']=P.digest(changed)
        with self.assertRaisesRegex(ValueError,'Data bytes, relocations'):P.equivalence(manifest)

    def test_unwind_change_without_instruction_change_fails(self):
        manifest=self.normal();path=Path(manifest['units'][1]['object']['path'])
        changed=path.with_name(path.stem+'-unwind.obj');raw=bytearray(path.read_bytes())
        sections=struct.unpack_from('<H',raw,2)[0]
        for sid in range(sections):
            at=20+sid*40
            if raw[at:at+8].rstrip(b'\0')==b'.xdata':
                offset=struct.unpack_from('<I',raw,at+20)[0];raw[offset+1]^=1;break
        else:self.fail('The frame fixture emitted no actual unwind bytes')
        changed.write_bytes(raw);manifest['units'][1]['object']=P.digest(changed)
        with self.assertRaisesRegex(ValueError,'unwind bytes'):P.equivalence(manifest)

    def test_cross_procedure_short_jump_cannot_silently_grow(self):
        jump='boom_jump PROC\n jmp boom_jump_body\nboom_jump ENDP\n'
        body='boom_jump_body PROC\n ret\nboom_jump_body ENDP\n'
        original=self.asm('short-original',DATA+'.code\nPUBLIC boom_jump\nPUBLIC boom_jump_body\n'+jump+body)
        data=self.asm('short-data',DATA)
        first=self.asm('short-first','EXTERN boom_jump_body:PROC\n.code\nPUBLIC boom_jump\n'+jump)
        second=self.asm('short-second','.code\nPUBLIC boom_jump_body\n'+body)
        manifest=dict(monolithic_object=P.digest(original),functions={'boom_jump':None,'boom_jump_body':None},framed_functions=[],
                      units=[dict(object=P.digest(p)) for p in (data,first,second)])
        with self.assertRaisesRegex(ValueError,'Machine code'):P.equivalence(manifest)

    def test_cross_procedure_near_jump_cannot_silently_shrink(self):
        jump='boom_jump PROC\n jmp boom_jump_body\nboom_jump ENDP\n'
        pad='boom_padding PROC\n REPT 256\n nop\n ENDM\n ret\nboom_padding ENDP\n'
        body='boom_jump_body PROC\n ret\nboom_jump_body ENDP\n'
        original=self.asm('near-original',DATA+'.code\nPUBLIC boom_jump\nPUBLIC boom_padding\nPUBLIC boom_jump_body\n'+jump+pad+body)
        data=self.asm('near-data',DATA)
        pair=self.asm('near-pair','.code\nPUBLIC boom_jump\nPUBLIC boom_jump_body\n'+jump+body)
        padding=self.asm('near-padding','.code\nPUBLIC boom_padding\n'+pad)
        manifest=dict(monolithic_object=P.digest(original),functions={'boom_jump':None,'boom_padding':None,'boom_jump_body':None},
                      framed_functions=[],units=[dict(object=P.digest(p)) for p in (data,pair,padding)])
        with self.assertRaisesRegex(ValueError,'Machine code'):P.equivalence(manifest)

    def test_whole_original_procedures_merge_to_preserve_near_width(self):
        jump='boom_jump PROC\n jmp boom_jump_body\nboom_jump ENDP\n'
        pad='boom_padding PROC\n REPT 256\n nop\n ENDM\n ret\nboom_padding ENDP\n'
        body='boom_jump_body PROC\n ret\nboom_jump_body ENDP\n'
        original=self.asm('merge-original',DATA+'.code\nPUBLIC boom_jump\nPUBLIC boom_padding\nPUBLIC boom_jump_body\n'+jump+pad+body)
        coff=P.Coff(original);source=original.with_suffix('.asm').read_bytes()
        B=P.load_module('candidate_merge_test_ranges','batch-source.py');spans=B.procedure_spans(source)
        index={n:i for i,n in enumerate(spans)}
        units,merges=P.preserve_transfer_widths([['boom_jump','boom_jump_body'],['boom_padding']],
            spans,index,coff,['boom_jump'])
        self.assertEqual(units,[['boom_jump','boom_padding','boom_jump_body']])
        self.assertEqual(len(merges),1)
        data=self.asm('merge-data',DATA)
        code=self.asm('merge-code','.code\nPUBLIC boom_jump\nPUBLIC boom_padding\nPUBLIC boom_jump_body\n'+jump+pad+body)
        manifest=dict(monolithic_object=P.digest(original),functions={n:None for n in spans},framed_functions=[],
                      units=[dict(object=P.digest(p)) for p in (data,code)])
        self.assertTrue(P.equivalence(manifest)['verified'])

    def test_source_comment_change_is_rejected_even_if_code_bytes_would_match(self):
        fixture=self.normal();directory=self.output/(self.id().split('.')[-1]+'-source')
        directory.mkdir();original=Path(fixture['monolithic_object']['path'])
        raw=original.with_suffix('.asm').read_bytes()
        (directory/'initialization-closure.asm').write_bytes(raw)
        (directory/'initialization-closure.obj').write_bytes(original.read_bytes())
        B=P.load_module('candidate_source_hash_test_ranges','batch-source.py');spans=B.procedure_spans(raw)
        hashes={n:hashlib.sha256(P.normalized_source(raw[a:b])).hexdigest() for n,(a,b) in spans.items()}
        (directory/'closure.json').write_text(json.dumps(dict(selected_function_sha256=hashes)))
        output=directory/'split';output.mkdir();manifest=P.prepare(directory,output,8*1024*1024)
        self.assertTrue(P.verify_source_preservation(manifest))
        unit=next(u for u in manifest['units'] if 'boom_first' in u['functions'])
        path=Path(unit['assembly']['path']);data=path.read_bytes()
        changed=data.replace(b'boom_first PROC FRAME',b'boom_first PROC FRAME ; changed source comment',1)
        self.assertNotEqual(changed,data);path.write_bytes(changed);unit['assembly']=P.digest(path)
        with self.assertRaisesRegex(ValueError,'complete source function bytes'):P.verify_source_preservation(manifest)


if __name__=='__main__':unittest.main()
