"""Actual small COFF cases for the narrow entirely-leaf diagnostic domain."""
import ast
from copy import deepcopy
import hashlib
import importlib.util
import inspect
from pathlib import Path
import struct
import subprocess
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
ML64=Path('D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/ml64.exe')

def module(name):
    spec=importlib.util.spec_from_file_location('leaf_unit_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

L=module('diagnostic-leaf-machine');O=module('jimage-owner-candidate')

def coff(raw):
    machine,count,_,symbols,number,optional,_=struct.unpack_from('<HHIIIHH',raw)
    if machine!=0x8664 or optional:raise ValueError('Fixture must be AMD64 COFF')
    strings=symbols+number*18;sections={}
    for i in range(count):
        at=20+40*i;name=raw[at:at+8].rstrip(b'\0').decode()
        size,data,relocations=struct.unpack_from('<III',raw,at+16);n=struct.unpack_from('<H',raw,at+32)[0]
        sections[name]=dict(header=at,size=size,data=data,relocations=relocations,count=n)
    rows={};index=0
    while index<number:
        at=symbols+18*index;name,value,section,kind,storage,aux=struct.unpack_from('<8sIhHBB',raw,at)
        if name[:4]==b'\0'*4:
            offset=struct.unpack_from('<I',name,4)[0];name=raw[strings+offset:raw.index(b'\0',strings+offset)]
        else:name=name.rstrip(b'\0')
        rows[name.decode()]=dict(index=index,offset=at,value=value,section=section,storage=storage,aux=aux)
        index+=aux+1
    return sections,rows


@unittest.skipUnless(ML64.is_file(),'Real ml64 required for diagnostic leaf COFF tests')
class DiagnosticLeafMachine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=ROOT/'.boom/diagnostic-leaf-tests'/uuid4().hex;cls.directory.mkdir(parents=True)
        cls.counter=0
        cls.source=b'''option casemap:none
.data
PUBLIC boom_fixture_data
PUBLIC boom_fixture_other
boom_fixture_data DWORD 0
boom_fixture_other DWORD 0
.code
PUBLIC boom_fixture_leaf
boom_fixture_leaf PROC
 test rcx,rcx
 jz fixture_done
 lea rdx,boom_fixture_data
 mov DWORD PTR [rcx],7
fixture_done:
 xor eax,eax
 ret
boom_fixture_leaf ENDP
PUBLIC boom_fixture_tail
boom_fixture_tail PROC
 jmp boom_fixture_leaf
boom_fixture_tail ENDP
END
'''
        cls.actual=cls.assemble(cls.source);cls.canonical=cls.assemble(cls.source)
        cls.raw=cls.actual.read_bytes();cls.sections,cls.symbols=coff(cls.raw)

    @classmethod
    def assemble(cls,source):
        number=cls.counter;cls.counter+=1;asm,obj=cls.directory/f'fixture-{number}.asm',cls.directory/f'fixture-{number}.obj'
        asm.write_bytes(source)
        result=subprocess.run([str(ML64),'/nologo','/c','/Fo'+str(obj),str(asm)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        if result.returncode:raise AssertionError(result.stdout.decode(errors='replace'))
        return obj

    def simple(self,body,*,prefix=''):
        source=('option casemap:none\n'+prefix+'.code\nPUBLIC boom_fixture_test\nboom_fixture_test PROC\n'+body+
            '\nboom_fixture_test ENDP\nEND\n').encode()
        return self.assemble(source),source

    def rejected(self,body,*,prefix=''):
        obj,source=self.simple(body,prefix=prefix)
        with self.assertRaises(ValueError):L.leaf_stop_coff(obj,source)

    def changed(self,raw):
        target=self.directory/('mutated-'+uuid4().hex+'.obj');target.write_bytes(raw);return target

    def test_positive_complete_COMPARISON_preserves_real_data_relocations(self):
        normalized,leaf=L.leaf_stop_coff(self.actual,self.source)
        self.assertEqual(normalized['imports'],[])
        self.assertTrue(any(r['relocations'] for r in normalized['sections'].values()))
        self.assertTrue(leaf['all_other_complete_reader_AST_unchanged'])
        proof=L.verify(self.actual,self.canonical,self.source)
        self.assertEqual(proof,L.verify(self.actual,self.canonical,self.source))
        self.assertTrue(proof['verified']);self.assertFalse(proof['full_source_selection_reverified'])
        self.assertFalse(proof['native_provider_unwind_policy_changed'])

    def test_private_reader_removes_only_the_final_owner_unwind_guard(self):
        expected=ast.parse(inspect.getsource(O.normalized_coff));function=expected.body[0]
        original=ast.dump(function,include_attributes=False);self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),L.OWNER_READER_AST_SHA256)
        removed=function.body.pop(-2)
        self.assertIsInstance(removed,ast.Expr);self.assertEqual(removed.value.args[1].value,L.UNWIND_CHECK)
        captured=[];real_compile=compile
        def observe(source,filename,mode,*args,**kwargs):
            if filename=='<complete_reader_pure_leaf_diagnostic_domain>':captured.append(deepcopy(source))
            return real_compile(source,filename,mode,*args,**kwargs)
        with patch('builtins.compile',side_effect=observe):reader,before=L._reader()
        self.assertEqual(before,original);self.assertEqual(len(captured),1)
        self.assertEqual(ast.dump(captured[0],include_attributes=False),ast.dump(expected,include_attributes=False))
        self.assertEqual(reader(self.actual),L.leaf_stop_coff(self.actual,self.source)[0])
        with self.assertRaisesRegex(ValueError,'unwind'):O.normalized_coff(self.actual)

    def test_actual_CALL_push_pop_and_implicit_stack_ops_rejected(self):
        # Encode bytes so source-token filtering cannot conceal a machine gap.
        for code in (' DB 0E8h,0,0,0,0\n ret',' DB 050h\n ret',' DB 058h\n ret',
                     ' DB 066h,050h\n ret',' DB 09Ch\n ret',' DB 0C8h,8,0,0\n ret',
                     ' DB 0C9h\n ret',' xchg rsp,rax\n ret',' sub rsp,32\n ret'):
            with self.subTest(code=code):self.rejected(code)

    def test_RET_immediate_and_far_RET_cannot_rely_on_Capstone_implicit_writes(self):
        for code in (' DB 0C2h,8,0',' DB 0C2h,0,0',' DB 0CBh',' DB 048h,0CBh',' DB 048h,0CFh'):
            with self.subTest(code=code):self.rejected(code)

    def test_nonvolatile_subregister_and_SIMD_alias_writes_rejected(self):
        for code in ('xor ebx,ebx','mov bh,0','xor r12d,r12d','mov sil,0',
                     'pxor xmm6,xmm6','vpxor ymm6,ymm6,ymm6','vzeroall'):
            with self.subTest(code=code):self.rejected(' '+code+'\n ret')

    def test_stack_memory_access_rejected_even_without_SP_write(self):
        for code in (' mov rax,QWORD PTR [rsp]\n ret',' mov DWORD PTR [rbp+8],1\n ret'):
            with self.subTest(code=code):self.rejected(code)

    def test_every_executable_byte_is_consumed(self):
        self.rejected(' ret\n DB 0Fh')

    def test_unresolved_import_or_indirect_jump_rejected(self):
        self.rejected(' jmp external_function',prefix='EXTERN external_function:PROC\n')
        self.rejected(' jmp rax')

    def test_loop_relative_group_is_checked_even_without_JUMP_group(self):
        for encoded in ('0E2h','0E1h','0E0h','0E3h'):
            with self.subTest(encoded=encoded):self.rejected(' DB '+encoded+',080h\n ret')
        obj,source=self.simple(' mov ecx,2\nfixture_again:\n nop\n loop fixture_again\n ret')
        _,proof=L.leaf_stop_coff(obj,source);self.assertGreater(proof['local_direct_jumps'],0)

    def test_branch_target_must_be_an_instruction_boundary(self):
        self.rejected(' DB 0EBh,1\n mov eax,11223344h\n ret')

    def test_actual_data_JMP_relocation_cannot_pass_raw_boundary_check(self):
        prefix='.data\ndata_target BYTE 0\n'
        for code in (' jmp NEAR PTR data_target\n ret',' DB 0E9h\n DD IMAGEREL data_target\n ret',
                     ' DB 0E9h\n DD data_target\n ret'):
            with self.subTest(code=code):self.rejected(code,prefix=prefix)

    def test_relocation_starting_before_branch_cannot_rewrite_its_bytes(self):
        raw=bytearray(self.raw);text=self.sections['.text' if '.text' in self.sections else '.text$mn']
        self.assertGreater(text['count'],0)
        # The first conditional branch follows test rcx,rcx at offset 3.
        # A coherent ADDR64 relocation beginning at 1 overlaps that branch.
        at=text['relocations'];struct.pack_into('<I',raw,at,1);struct.pack_into('<H',raw,at+8,1)
        with self.assertRaises(ValueError):L.leaf_stop_coff(self.changed(raw),self.source)

    def test_leaf_with_unwind_tables_cannot_relax_the_native_domain(self):
        source=b'option casemap:none\n.code\nPUBLIC boom_fixture_frame\nboom_fixture_frame PROC FRAME\n .endprolog\n ret\nboom_fixture_frame ENDP\nEND\n'
        obj=self.assemble(source)
        # A caller-supplied text claim cannot hide real .pdata/.xdata.
        with self.assertRaises(ValueError):L.leaf_stop_coff(obj,b'; leaf claim only\n')

    def test_full_compare_keeps_instruction_flags_auxiliary_and_relocation_targets(self):
        text=self.sections['.text' if '.text' in self.sections else '.text$mn']
        mutations=[];raw=bytearray(self.raw);raw[text['data']+2]^=0x1b;mutations.append(raw)
        data=self.sections['.data'];raw=bytearray(self.raw);flags=struct.unpack_from('<I',raw,data['header']+36)[0]
        struct.pack_into('<I',raw,data['header']+36,flags^0x80000000);mutations.append(raw)
        section_symbol=next(r for n,r in self.symbols.items() if n=='.data' and r['aux'])
        raw=bytearray(self.raw);raw[section_symbol['offset']+18+8]^=1;mutations.append(raw)
        raw=bytearray(self.raw);struct.pack_into('<I',raw,text['relocations']+4,self.symbols['boom_fixture_other']['index']);mutations.append(raw)
        for i,raw in enumerate(mutations):
            with self.subTest(mutation=i),self.assertRaises(ValueError):L.verify(self.changed(raw),self.canonical,self.source)


if __name__=='__main__':unittest.main()
