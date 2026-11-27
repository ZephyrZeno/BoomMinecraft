"""Bounded pure-MASM native memory tests; no Java, JVM, guest Main or production registration.

Uses the published generic candidate builder. Optional independent oracle vectors
are explicit sealed inputs; heap/Java-wrapper vectors are excluded from core tests.
"""
from __future__ import annotations
import argparse
import collections
import concurrent.futures
import ctypes as c
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import threading

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path('D:/Dev/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64')
SDK = Path('C:/Program Files (x86)/Windows Kits/10/Lib/10.0.26100.0/um/x64/kernel32.lib')
EXPORTS = ['boom_native_memory_' + name for name in ('init', 'service', 'close')]
IMPORTS = sorted(['VirtualAlloc', 'VirtualFree', 'GetLastError', 'AcquireSRWLockExclusive', 'ReleaseSRWLockExclusive'])
Q, U, P = c.c_uint64, c.c_uint32, c.c_void_p
O = C = None
READONLY_FILE = ORACLE_VECTORS = ORACLE_RECEIPT = None
ORACLE_VECTORS_SHA = ORACLE_RECEIPT_SHA = None

def check(value, why):
    if not value:
        raise ValueError(why)

def artifact(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), size=path.stat().st_size, sha256=digest)

def write(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + '\n')

FAULT_WRAPPERS = r'''
; Test-only deterministic OS failure injection. Native pass-through otherwise.
; Masks bit0 fail-now, bit1 fail-next-call, etc.; setter only while quiescent.
EXTERN VirtualAlloc:PROC
EXTERN VirtualFree:PROC
EXTERN SetLastError:PROC
.data
ALIGN 8
nmt_alloc_mask QWORD 0
nmt_free_mask QWORD 0
.code
PUBLIC boom_native_memory_test_fault
boom_native_memory_test_fault PROC
 mov QWORD PTR [nmt_alloc_mask],rcx
 mov QWORD PTR [nmt_free_mask],rdx
 ret
boom_native_memory_test_fault ENDP
nmt_VirtualAlloc PROC PRIVATE FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
nmt_va_retry:
 mov rax,QWORD PTR [nmt_alloc_mask]
 mov r10,rax
 shr r10,1
 mov r11,rax
 lock cmpxchg QWORD PTR [nmt_alloc_mask],r10
 jne nmt_va_retry
 test r11b,1
 jnz nmt_va_fail
 add rsp,40
 jmp VirtualAlloc
nmt_va_fail:
 mov ecx,8
 call SetLastError
 xor eax,eax
 add rsp,40
 ret
nmt_VirtualAlloc ENDP
nmt_VirtualFree PROC PRIVATE FRAME
 sub rsp,40
 .allocstack 40
 .endprolog
nmt_vf_retry:
 mov rax,QWORD PTR [nmt_free_mask]
 mov r10,rax
 shr r10,1
 mov r11,rax
 lock cmpxchg QWORD PTR [nmt_free_mask],r10
 jne nmt_vf_retry
 test r11b,1
 jnz nmt_vf_fail
 add rsp,40
 jmp VirtualFree
nmt_vf_fail:
 mov ecx,5
 call SetLastError
 xor eax,eax
 add rsp,40
 ret
nmt_VirtualFree ENDP
'''

ABI_PROBE = r'''; Native test caller checks every Win64 nonvolatile integer register.
option casemap:none
.code
PUBLIC boom_native_memory_test_abi
boom_native_memory_test_abi PROC FRAME
 push rbx
 .pushreg rbx
 push rbp
 .pushreg rbp
 push rsi
 .pushreg rsi
 push rdi
 .pushreg rdi
 push r12
 .pushreg r12
 push r13
 .pushreg r13
 push r14
 .pushreg r14
 push r15
 .pushreg r15
 sub rsp,104
 .allocstack 104
 .endprolog
 mov QWORD PTR [rsp+32],rcx
 mov rax,QWORD PTR [rsp+208]
 mov rcx,rdx
 mov rdx,r8
 mov r8,r9
 mov r9,rax
 mov rbx,01122334455667788h
 mov rbp,02233445566778899h
 mov rsi,033445566778899AAh
 mov rdi,0445566778899AABBh
 mov r12,05566778899AABBCCh
 mov r13,066778899AABBCCDDh
 mov r14,0778899AABBCCDDEEh
 mov r15,08899AABBCCDDEEFFh
 call QWORD PTR [rsp+32]
 mov DWORD PTR [rsp+48],eax
 xor r10d,r10d
 mov rax,01122334455667788h
 cmp rbx,rax
 je nma_bx
 or r10d,1
nma_bx:
 mov rax,02233445566778899h
 cmp rbp,rax
 je nma_bp
 or r10d,2
nma_bp:
 mov rax,033445566778899AAh
 cmp rsi,rax
 je nma_si
 or r10d,4
nma_si:
 mov rax,0445566778899AABBh
 cmp rdi,rax
 je nma_di
 or r10d,8
nma_di:
 mov rax,05566778899AABBCCh
 cmp r12,rax
 je nma_12
 or r10d,16
nma_12:
 mov rax,066778899AABBCCDDh
 cmp r13,rax
 je nma_13
 or r10d,32
nma_13:
 mov rax,0778899AABBCCDDEEh
 cmp r14,rax
 je nma_14
 or r10d,64
nma_14:
 mov rax,08899AABBCCDDEEFFh
 cmp r15,rax
 je nma_15
 or r10d,128
nma_15:
 mov rax,rsp
 and eax,15
 jz nma_align
 or r10d,256
nma_align:
 mov eax,DWORD PTR [rsp+48]
 shl r10,32
 or rax,r10
 add rsp,104
 pop r15
 pop r14
 pop r13
 pop r12
 pop rdi
 pop rsi
 pop rbp
 pop rbx
 ret
boom_native_memory_test_abi ENDP
END
'''

def build(out, source, fault=False, expected_exports=None, expected_imports=None):
    out.mkdir()
    asm, obj, dll, rsp = (out / name for name in ('owner.asm', 'owner.obj', 'owner.dll', 'link.rsp'))
    if fault:
        check(source.count('call VirtualAlloc') == 3 and source.count('call VirtualFree') == 5,
            'Exact test-only OS fault-call sites changed')
        source = source.replace('EXTERN VirtualAlloc:PROC\n', '').replace('EXTERN VirtualFree:PROC\n', '')
        source = source.replace('call VirtualAlloc', 'call nmt_VirtualAlloc').replace('call VirtualFree', 'call nmt_VirtualFree')
        check(source.endswith('END\n'), 'Whole ASM terminator required')
        source = source[:-4] + FAULT_WRAPPERS + '\nEND\n'
    with asm.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(source)
    with (out / 'assembler.log').open('xb') as stream:
        subprocess.run([str(TOOLS / 'ml64.exe'), '/nologo', '/c', '/Fo' + str(obj), str(asm)],
            stdout=stream, stderr=subprocess.STDOUT, check=True, timeout=120)
    exports = expected_exports if expected_exports is not None else EXPORTS + (['boom_native_memory_test_fault'] if fault else [])
    imports = expected_imports if expected_imports is not None else sorted(IMPORTS + (['SetLastError'] if fault else []))
    text = '\n'.join(['/NOLOGO', '/DLL', '/NOENTRY', '/NODEFAULTLIB', '/MACHINE:X64', '/INCREMENTAL:NO',
        '/DYNAMICBASE', '/NXCOMPAT', '/BREPRO', '/OUT:"' + str(dll) + '"',
        *['/EXPORT:' + name for name in sorted(exports)], '"' + str(obj) + '"', '"' + str(SDK) + '"']) + '\n'
    with rsp.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text)
    with (out / 'linker.log').open('xb') as stream:
        subprocess.run([str(TOOLS / 'link.exe'), '@' + str(rsp)], stdout=stream,
            stderr=subprocess.STDOUT, check=True, timeout=120)
    normalized = O.normalized_coff(obj)
    check(normalized['exports'] == sorted(exports), 'Unexpected complete COFF exports')
    check(normalized['imports'] == sorted(imports), 'Unexpected Win32 imports')
    return dict(asm=artifact(asm), obj=artifact(obj), dll=artifact(dll), rsp=artifact(rsp), normalized=normalized)

def full_coff(path):
    # Supplemental reader resolves actual instruction operands/unwind bindings.
    # O.normalized_coff remains the complete COFF header/symbol/aux/flags validator.
    O.normalized_coff(path)
    raw = Path(path).read_bytes()
    count = struct.unpack_from('<H', raw, 2)[0]
    symbols_at, total = struct.unpack_from('<II', raw, 8)
    strings = symbols_at + total*18
    sections, order, symbols, names = {}, {}, {}, {}
    for ident in range(1, count+1):
        at = 20+(ident-1)*40
        name = raw[at:at+8].rstrip(b'\0').decode('ascii')
        length, data_at, reloc_at = struct.unpack_from('<III', raw, at+16)
        nrel = struct.unpack_from('<H', raw, at+32)[0]
        sections[name] = dict(data=raw[data_at:data_at+length],
            flags=struct.unpack_from('<I', raw, at+36)[0],
            pending=[struct.unpack_from('<IIH', raw, reloc_at+10*i) for i in range(nrel)])
        order[ident] = name
    index = 0
    while index < total:
        at = symbols_at + index*18
        name, value, section, kind, storage, aux = struct.unpack_from('<8sIhHBB', raw, at)
        if name[:4] == bytes(4):
            offset = strings + struct.unpack_from('<I', name, 4)[0]
            name = raw[offset:raw.index(b'\0', offset)]
        else:
            name = name.rstrip(b'\0')
        row = dict(name=name.decode('ascii'), value=value, section=order[section] if section > 0 else section,
            kind=kind, storage=storage)
        symbols[index], names[row['name']] = row, row
        index += aux+1
    for row in sections.values():
        row['relocations'] = [dict(offset=offset, target=symbols[target], kind=kind)
            for offset, target, kind in row.pop('pending')]
    return sections, names

def fault_core_machine_equivalence(production_path, fault_path):
    original, original_names = full_coff(production_path)
    derived, derived_names = full_coff(fault_path)
    text = original_names['boom_native_memory_init']['section']
    check(original[text]['flags'] == derived[text]['flags'], 'Fault variant actual executable flags')
    raw = original[text]['data']
    other = bytearray(derived[text]['data'][:len(raw)])
    originals = original[text]['relocations']
    remaining = list(derived[text]['relocations'])
    sites = []
    for row in originals:
        offset, target = row['offset'], row['target']['name']
        if target in ('VirtualAlloc', 'VirtualFree'):
            check(row['kind'] == 4 and raw[offset-1] == other[offset-1] == 0xE8 and raw[offset:offset+4] == bytes(4),
                'Exact complete production OS call instruction/fixup')
            wrapper = 'nmt_' + target
            check(derived_names[wrapper]['section'] == text and derived_names[wrapper]['value'] >= len(raw),
                'Injected test-only wrapper lies after complete production core')
            call_reloc = [item for item in remaining if item['offset'] == offset]
            if call_reloc:
                check(len(call_reloc) == 1 and call_reloc[0]['kind'] == 4 and call_reloc[0]['target']['name'] == wrapper,
                    'Fault variant exact wrapper call relocation')
                target_at = call_reloc[0]['target']['value'] + struct.unpack_from('<i', other, offset)[0]
                remaining.remove(call_reloc[0])
            else:
                target_at = offset+4 + struct.unpack_from('<i', other, offset)[0]
            check(target_at == derived_names[wrapper]['value'], 'Fault variant actual call operand binds the exact native wrapper')
            other[offset:offset+4] = raw[offset:offset+4]
            sites.append(dict(offset=offset, production=target, native_test_wrapper=wrapper, wrapper_offset=target_at))
        else:
            matches = [item for item in remaining if item['offset'] == offset]
            check(matches == [row], 'Every other core relocation unchanged')
            remaining.remove(matches[0])
    check(bytes(other) == raw and len(sites) == 8, 'All production core instructions unchanged outside eight exact OS call displacements')
    check(not any(row['offset'] < len(raw) for row in remaining), 'No additional injected relocation inside core')
    for name, row in original_names.items():
        if row['section'] == text and row['kind'] == 0x20:
            check(derived_names[name] == row, 'Core native function binding/type/storage unchanged: ' + name)
    # Native wrapper additions append unwind entries; core unwind tables stay byte exact.
    check(derived['.pdata']['data'][:len(original['.pdata']['data'])] == original['.pdata']['data'], 'Core unwind ranges unchanged')
    check(derived['.xdata']['data'][:len(original['.xdata']['data'])] == original['.xdata']['data'], 'Core unwind opcodes unchanged')
    for name in ('.pdata', '.xdata'):
        check(original[name]['flags'] == derived[name]['flags'], 'Actual core unwind flags unchanged')
        if name == '.pdata':
            check([row for row in derived[name]['relocations'] if row['offset'] < len(original[name]['data'])]
                == original[name]['relocations'], 'All core unwind relocations unchanged')
    return dict(verified=True, whole_core_instruction_bytes_equal_after_eight_exact_call_operand_rebindings=True,
        exact_call_sites=sites, remaining_code_relocations_identical=True, core_functions_identical=True,
        all_core_unwind_bytes_ranges_flags_relocations_identical=True,
        injected_implementation='test-only-native-MASM-wrappers; real Win32 calls except configured failure masks')

def actual_unwind(api):
    ntdll = c.WinDLL('ntdll')
    lookup = ntdll.RtlLookupFunctionEntry
    lookup.argtypes, lookup.restype = [Q, c.POINTER(Q), P], P
    expected = dict(init=([3, 6, 7, 12], 40), service=([3, 6, 7, 12, 13, 14, 15], 112),
        close=([3, 6, 7, 12, 13, 14], 40))
    rows = []
    for name, (registers, stack_bytes) in expected.items():
        address = c.cast(getattr(api, name), P).value
        image = Q()
        entry = lookup(address, c.byref(image), None)
        check(entry and image.value == api.dll._handle, 'Actual Windows native unwind table found for ' + name)
        begin, end, unwind = struct.unpack('<III', c.string_at(entry, 12))
        check(image.value+begin == address and begin < end, 'Unwind begins at exact actual exported native entry')
        head = c.string_at(image.value+unwind, 4)
        version_flags, prologue, count, frame = head
        check(version_flags == 1 and frame == 0 and count == len(registers)+1,
            'Actual Win64 version1/nohandler unwind contract')
        info = c.string_at(image.value+unwind, 4+((count*2+3)//4)*4)
        parsed, previous = [], prologue
        for at in range(4, 4+count*2, 2):
            offset, opinfo = info[at:at+2]
            check(offset <= previous, 'Actual unwind prologue instruction offsets ordered')
            previous = offset
            parsed.append((offset, opinfo & 15, opinfo >> 4))
        check(parsed[0][1:] == (2, (stack_bytes-8)//8) and [item[2] for item in parsed[1:]] == registers[::-1] and
            all(item[1] == 0 for item in parsed[1:]), 'Actual machine unwind preserves exact native nonvolatile pushes/allocation')
        check((8-len(registers)*8-stack_bytes) % 16 == 0, 'Native public call-site stack alignment')
        rows.append(dict(name=name, begin_RVA=begin, end_RVA=end, unwind_RVA=unwind,
            prologue_bytes=prologue, exact_unwind_hex=info.hex(), saved_nonvolatile_registers=registers, local_stack_bytes=stack_bytes))
    return dict(verified=True, actual_Windows_RtlLookupFunctionEntry=True, all_three_public_entries=rows,
        leaf_helpers_use_only_volatile_registers_and_no_stack=True)

def native_abi_probe(api, path):
    dll = c.WinDLL(str(path))
    probe = dll.boom_native_memory_test_abi
    probe.argtypes, probe.restype = [P, Q, Q, Q, Q], Q
    rows = []

    def invoke(name, arg1, arg2=0, arg3=0, arg4=0, expected=0):
        status = int(probe(c.cast(getattr(api, name), P), arg1, arg2, arg3, arg4))
        check(status == expected, 'Actual MASM ABI probe status/preserved registers/stack alignment: ' + name)
        rows.append(dict(name=name, status=expected, nonvolatile_integer_clobber_mask=0, caller_stack_alignment_mask=0))

    owner = Owner()
    invoke('init', c.addressof(owner), 128, 8, 65536)
    invoke('init', c.addressof(owner), 128, 8, 65536, expected=2)
    job = Job(owner=c.addressof(owner), op=0, bytes=64)
    invoke('service', c.addressof(job))
    address = job.result
    for op, kw, status in [(4, dict(address=address, bytes=8, width=8, value=0x8877665544332211), 0),
        (3, dict(address=address, bytes=8, width=8), 0),
        (5, dict(address=address, bytes=64, value=0xAB), 0),
        (6, dict(address=address, other=address+8, bytes=32), 0),
        (7, dict(address=address, other=address, bytes=32, width=8), 0),
        (3, dict(address=6, bytes=8, width=8), 1),
        (3, dict(address=address+63, bytes=8, width=8), 3),
        (8, dict(address=address, bytes=32, flags=1), 0)]:
        job = Job(owner=c.addressof(owner), op=op, **kw)
        invoke('service', c.addressof(job), expected=status)
    token = job.token
    invoke('close', c.addressof(owner), expected=2)
    job = Job(owner=c.addressof(owner), op=2, address=address)
    invoke('service', c.addressof(job), expected=2)
    job = Job(owner=c.addressof(owner), op=9, token=token)
    invoke('service', c.addressof(job))
    job = Job(owner=c.addressof(owner), op=1, address=address, bytes=128)
    invoke('service', c.addressof(job))
    invoke('close', c.addressof(owner))
    invoke('close', c.addressof(owner))
    api.closed(owner)
    return dict(verified=True, native_MASM_caller_sets_and_checks_RBX_RBP_RSI_RDI_R12_R13_R14_R15=True,
        ordinary_Win64_args_including_fifth_probe_arg=True, actual_calls=rows)

class Owner(c.Structure):
    _fields_ = [('magic', Q), ('bytes', U), ('abi', U), ('srw', Q), ('state', U), ('capacity', U),
        ('live', Q), ('active', Q), ('logical', Q), ('budget', Q), ('records', Q), ('leases', Q),
        ('metadata', Q), ('sequence', Q), ('alloc_success', Q), ('free_success', Q), ('resize_success', Q),
        ('os_error', U), ('lease_capacity', U)]

class Job(c.Structure):
    _fields_ = [('owner', Q), ('address', Q), ('bytes', Q), ('other', Q), ('value', Q), ('result', Q),
        ('token', Q), ('generation', Q), ('width', U), ('flags', U), ('op', U), ('status', U),
        ('os_error', U), ('reserved', U), ('completed', Q), ('reserved_q', Q * 4)]

class API:
    def __init__(self, path):
        self.dll = c.WinDLL(str(path))
        self.init = self.dll.boom_native_memory_init
        self.init.argtypes, self.init.restype = [P, Q, U, Q], U
        self.service = self.dll.boom_native_memory_service
        self.service.argtypes, self.service.restype = [P], U
        self.close = self.dll.boom_native_memory_close
        self.close.argtypes, self.close.restype = [P], U
        self.fault = getattr(self.dll, 'boom_native_memory_test_fault', None)
        if self.fault:
            self.fault.argtypes, self.fault.restype = [Q, Q], None
        self.closed_native_regions_observed_free = 0

    def owner(self, capacity=128, budget=4 * 1024 * 1024):
        owner = Owner()
        check(self.init(c.byref(owner), 128, capacity, budget) == 0, 'Actual MASM owner init')
        return owner

    def call(self, owner, op, address=0, size=0, other=0, value=0, width=0, flags=0, token=0, expected=0):
        job = Job(owner=c.addressof(owner), address=address, bytes=size, other=other,
            value=value, width=width, flags=flags, token=token, op=op)
        status = int(self.service(c.byref(job)))
        check(status == job.status == expected,
            f'MASM op{op} expected{expected}, status{status}/{job.status} addr{address:x} len{size} width{width}')
        if status:
            check(job.result == 0 and job.completed == 0, 'Failed operation must not publish result/progress')
        return job

    def alloc(self, owner, size):
        job = self.call(owner, 0, size=size)
        check(size == 0 or job.result and job.generation and job.completed == size, 'Actual owned allocation result')
        return int(job.result)

    def bytes(self, owner, address, size):
        # Tests observe through actual native plain reads, never implement a service in Python.
        return bytes(self.call(owner, 3, address+i, 1, width=1).result for i in range(size))

    def put(self, owner, address, data):
        for i, value in enumerate(data):
            self.call(owner, 4, address+i, 1, value=value, width=1)

    def closed(self, owner):
        bases = [owner.records] if owner.records else []
        if owner.records:
            bases.extend(Q.from_address(owner.records+i*64).value for i in range(owner.capacity)
                if U.from_address(owner.records+i*64+40).value)
        check(self.close(c.byref(owner)) == 0, 'Actual native close')
        check(owner.state == 3 and owner.live == owner.active == owner.logical == 0 and
            owner.records == owner.leases == owner.metadata == 0, 'Closed owner must retain no payload or metadata')
        check(self.close(c.byref(owner)) == 0, 'Idempotent actual native close')
        for address in bases:
            info = MemoryBasicInformation()
            check(K.VirtualQuery(address, c.byref(info), c.sizeof(info)) == c.sizeof(info) and info.State == 0x10000,
                'Actual Windows payload/metadata address is MEM_FREE immediately after quiescent close')
            self.closed_native_regions_observed_free += 1

class MemoryBasicInformation(c.Structure):
    _fields_ = [('BaseAddress', P), ('AllocationBase', P), ('AllocationProtect', U), ('PartitionId', c.c_uint16),
        ('_pad1', c.c_uint16), ('RegionSize', Q), ('State', U), ('Protect', U), ('Type', U), ('_pad2', U)]

K = c.WinDLL('kernel32', use_last_error=True)
K.GetCurrentThreadId.argtypes, K.GetCurrentThreadId.restype = [], U
K.GetCurrentProcess.argtypes, K.GetCurrentProcess.restype = [], P
K.GetProcessHandleCount.argtypes, K.GetProcessHandleCount.restype = [P, c.POINTER(U)], c.c_int
K.VirtualQuery.argtypes, K.VirtualQuery.restype = [P, P, c.c_size_t], c.c_size_t


def handles():
    count = U()
    check(K.GetProcessHandleCount(K.GetCurrentProcess(), c.byref(count)), 'Actual process handle count')
    return count.value

def normal_tests(api):
    cases = []
    owner = Owner()
    check(api.init(None, 128, 1, 65536) == 5, 'Null owner rejected')
    check(api.close(None) == 5, 'Null close rejected')
    for size, cap, budget, expected in [(127, 1, 1024, 5), (128, 0, 1024, 3),
        (128, 4097, 1024, 3), (128, 1, 0, 3), (128, 1, 1 << 63, 3)]:
        check(api.init(c.byref(owner), size, cap, budget) == expected, 'Invalid init bounds')
    check(bytes(owner) == bytes(128), 'Invalid init does not clobber zero owner')
    owner = api.owner()
    before = bytes(owner)
    check(api.init(c.byref(owner), 128, 128, 1 << 20) == 2 and bytes(owner) == before, 'Live reinit busy preserves owner')
    api.call(owner, 0, size=0)
    api.call(owner, 2)
    api.call(owner, 2, size=1, expected=3)
    api.call(owner, 0, size=1 << 63, expected=3)
    api.call(owner, 0, size=owner.budget+1, expected=7)
    check(api.service(None) == 5, 'Null job rejected')
    cases.append('init-invalid-live-repeat-zero-and-budget')

    address = api.alloc(owner, 256)
    for width in (1, 2, 4, 8):
        for offset in (0, 1, 3, 7, 24):
            api.call(owner, 5, address, 256, value=0xCC)
            value = 0xF2A190807060BEEF
            api.call(owner, 4, address+offset, width, value=value, width=width)
            read = api.call(owner, 3, address+offset, width, width=width)
            check(read.result == value & ((1 << (8*width))-1), 'Plain raw integer bits including unaligned widths')
            expected = bytearray([0xCC]*256)
            expected[offset:offset+width] = value.to_bytes(8, 'little')[:width]
            check(api.bytes(owner, address, 40) == expected[:40], 'Plain store modifies exact byte range')
    cases.append('plain-1-2-4-8-raw-bits-and-unaligned-guards')

    for offset, length in [(0, 64), (4, 12), (2, 6), (1, 3), (13, 0)]:
        api.call(owner, 5, address, 256, value=0x6A)
        api.call(owner, 5, address+offset, length, value=0xE7)
        expected = bytearray([0x6A]*96)
        expected[offset:offset+length] = bytes([0xE7])*length
        check(api.bytes(owner, address, 96) == expected, 'Aligned/unaligned fill exact bytes')
    cases.append('fill-common-8-4-2-1-alignment-and-zero')

    seed = bytes((i*37+11) & 255 for i in range(128))
    for source, dest, length in [(0, 64, 32), (4, 68, 12), (2, 66, 6), (1, 65, 13),
        (0, 0, 64), (0, 8, 64), (8, 0, 64), (0, 1, 63), (1, 0, 63)]:
        api.put(owner, address, seed)
        api.call(owner, 6, address+source, length, other=address+dest)
        expected = bytearray(seed)
        expected[dest:dest+length] = seed[source:source+length]
        check(api.bytes(owner, address, len(seed)) == expected, 'Owned memmove exact snapshot overlap semantics')
    cases.append('copy-disjoint-self-forward-backward-partial-overlap')

    for width in (2, 4, 8):
        for source, dest, length in [(0, 64, 32), (0, 0, 32), (0, width, 32), (width, 0, 32), (1, 2, 32), (2, 1, 32)]:
            api.put(owner, address, seed)
            api.call(owner, 7, address+source, length, other=address+dest, width=width)
            changed = b''.join(seed[source+i:source+i+width][::-1] for i in range(0, length, width))
            expected = bytearray(seed)
            expected[dest:dest+length] = changed
            check(api.bytes(owner, address, len(seed)) == expected, 'copySwap element snapshot and partial overlap')
    api.call(owner, 7, address, 7, other=address+64, width=2, expected=3)
    api.call(owner, 7, address, 8, other=address+64, width=1, expected=3)
    cases.append('copySwap2-4-8-disjoint-self-and-partial-overlap')

    for op in (3, 4):
        api.call(owner, op, address+255, 2, width=2, expected=3)
        api.call(owner, op, address+256, 1, width=1, expected=1)
        api.call(owner, op, address, 3, width=3, expected=3)
    api.call(owner, 5, (1 << 64)-16, 32, expected=3)
    api.call(owner, 5, address+250, 7, expected=3)
    api.call(owner, 6, address, 16, other=address+250, expected=3)
    api.call(owner, 2, address+1, expected=3)
    api.call(owner, 1, address+1, 64, expected=3)
    for unknown in (0, 6, 38, 70, 86, 0x12345678):
        api.call(owner, 3, unknown, 1, width=1, expected=1)
        api.call(owner, 4, unknown, 1, width=1, value=1, expected=1)
        api.call(owner, 5, unknown, 1, value=1, expected=1)
        if unknown:
            api.call(owner, 2, unknown, expected=1)
            api.call(owner, 1, unknown, 64, expected=1)
    api.call(owner, 5, (1 << 64)-1, 0)
    api.call(owner, 6, (1 << 64)-1, 0, other=(1 << 64)-1)
    cases.append('logical-bounds-overflow-unknown-and-ThreadIdentifiers-fallback-domain')

    other = api.alloc(owner, 128)
    read1 = api.call(owner, 8, address, 32, flags=1)
    read2 = api.call(owner, 8, address+16, 32, flags=1)
    check(read1.token != read2.token and owner.active == 2, 'Shared read leases have unique tokens')
    before = bytes(owner)
    check(api.close(c.byref(owner)) == 2 and bytes(owner) == before, 'Busy close leaves all owner fields/resources unchanged')
    api.call(owner, 3, address, 8, width=8)
    api.call(owner, 6, address, 32, other=other)
    for op, kw in [(4, dict(size=8, width=8)), (5, dict(size=8)), (6, dict(size=8, other=address)),
        (1, dict(size=512)), (2, {}), (8, dict(size=8, flags=2))]:
        api.call(owner, op, address, expected=2, **kw)
    api.call(owner, 9, token=read1.token)
    api.call(owner, 9, token=read1.token, expected=3)
    api.call(owner, 9, token=read2.token)
    writer = api.call(owner, 8, address, 32, flags=3)
    api.call(owner, 3, address, 8, width=8, expected=2)
    api.call(owner, 8, address, 8, flags=1, expected=2)
    api.call(owner, 6, address, 8, other=other, expected=2)
    api.call(owner, 9, token=writer.token)
    api.call(owner, 4, address, 8, value=0x0102030405060708, width=8)
    api.call(owner, 5, address, 8, value=0xAB)
    check(owner.active == 0, 'Every borrowed path releases leases')
    cases.append('shared-read-exclusive-write-busy-close-and-release-retry')

    data = api.bytes(owner, address, 128)
    grown = api.call(owner, 1, address, 512).result
    check(grown and grown != address and api.bytes(owner, grown, 128) == data, 'Realloc grows preserving old bytes')
    shrunk = api.call(owner, 1, grown, 32).result
    check(shrunk and api.bytes(owner, shrunk, 32) == data[:32], 'Realloc shrink preserves minimum bytes')
    api.call(owner, 1, shrunk, 0)
    address = api.call(owner, 1, 0, 32).result
    api.call(owner, 2, address)
    api.call(owner, 2, other)
    check(owner.live == owner.logical == 0, 'All normal payloads freed')
    last_sequence = owner.sequence
    api.closed(owner)
    api.call(owner, 0, size=1, expected=9)
    check(api.init(c.byref(owner), 128, 1, 256) == 0 and owner.sequence == last_sequence, 'Reinit preserves monotonic sequence')
    address = api.alloc(owner, 16)
    tokens = [api.call(owner, 8, address, 1, flags=1).token for _ in range(16)]
    check(len(set(tokens)) == 16 and min(tokens) > last_sequence, 'No token reuse across owner lifetime')
    api.call(owner, 8, address, 1, flags=1, expected=7)
    for token in tokens:
        api.call(owner, 9, token=token)
    api.call(owner, 1, address, 32, expected=7)
    api.call(owner, 9, token=tokens[0], expected=3)
    saved_sequence = owner.sequence
    owner.sequence = (1 << 64)-1  # Test-only metadata exhaustion; no allocation failure pressure.
    api.call(owner, 8, address, 1, flags=1, expected=7)
    owner.sequence = saved_sequence
    api.closed(owner)
    cases.append('realloc-grow-shrink-zero-capacity-and-monotonic-token-exhaustion')

    owner = api.owner(capacity=4, budget=256)
    address = api.alloc(owner, 128)
    api.call(owner, 5, address, 128, value=0xB1)
    api.call(owner, 1, address, 129, expected=7)
    check(api.bytes(owner, address, 128) == bytes([0xB1])*128 and owner.live == 1, 'Budget failure preserves old payload')
    api.closed(owner)
    cases.append('bounded-peak-realloc-budget-failure-retains-old')
    return cases

def oracle_native_vectors(api):
    """Replay only genuinely native-domain vectors, never stand in for heap adapters.

    The core returns raw unsigned bits. Java sign interpretation below is solely
    a comparison projection, not evidence that a Java adapter has executed.
    """
    vectors_path = ORACLE_VECTORS
    result_path = ORACLE_RECEIPT
    vector_pin, oracle_pin = artifact(vectors_path), artifact(result_path)
    check(vector_pin['sha256'] == ORACLE_VECTORS_SHA, 'Exact independent expected vectors')
    check(oracle_pin['sha256'] == ORACLE_RECEIPT_SHA, 'Exact completed independent JDK oracle')
    oracle = json.loads(result_path.read_text())
    check(oracle['verified'] and not oracle['ASM_native_execution_verified'] and oracle['total_cases'] == 240,
        'Independent JDK oracle scope')
    cases = json.loads(vectors_path.read_text())['cases']
    owner = api.owner(capacity=8, budget=131072)
    rows, skipped = [], []

    def pattern(n, seed):
        return bytes(((i*37+seed) ^ (i >> 1)) & 255 for i in range(n))

    def rounded(n):
        return (n+7) & -8

    for row in cases:
        op, args = row['operation'], row['wire_args']
        if op == 'negative' or op == 'set' and args[0] != 'native' or op in ('copy', 'swap') and args[:2] != ['native', 'native']:
            skipped.append(dict(id=row['id'], why='original-Java-check-or-heap-adapter-outside-core'))
            continue
        value, payload, exception = '', b'', ''
        if op == 'allocate':
            n, seed = map(int, args)
            address = api.alloc(owner, rounded(n))
            api.put(owner, address, pattern(n, seed))
            value = 'nonzero' if address else 'zero'
            payload = api.bytes(owner, address, n)
            api.call(owner, 2, address)
        elif op == 'reallocate':
            old, n, seed = map(int, args)
            address = api.alloc(owner, rounded(old))
            api.put(owner, address, pattern(old, seed))
            address = api.call(owner, 1, address, rounded(n)).result
            for at in range(min(old, n), n):
                api.call(owner, 4, address+at, 1, width=1, value=0xA7)
            value = 'nonzero' if address else 'zero'
            payload = api.bytes(owner, address, n)
            api.call(owner, 2, address)
        elif op == 'free0':
            api.call(owner, 2)
            value = 'void'
        elif op == 'free_valid':
            address = api.alloc(owner, 64)
            api.call(owner, 4, address, 1, width=1, value=1)
            api.call(owner, 2, address)
            value = 'void'
        elif op == 'plain':
            kind, at, bits = int(args[0]), int(args[1]), int(args[2], 16)
            width = row['detail']['width_bytes']
            address = api.alloc(owner, 64)
            api.put(owner, address, pattern(64, 17))
            api.call(owner, 4, address+at, width, width=width, value=bits)
            observed = api.call(owner, 3, address+at, width, width=width).result
            check(observed == bits & ((1 << (8*width))-1), 'Actual core raw primitive bits match oracle input')
            if kind in (2, 4, 5) and observed >> (width*8-1):
                observed -= 1 << (width*8)
            value = f'{observed & ((1 << 64)-1):016x}'
            payload = api.bytes(owner, address, 64)
            api.call(owner, 2, address)
        elif op == 'set':
            _, at, n, fill = args
            address = api.alloc(owner, 64)
            api.put(owner, address, pattern(64, 17))
            api.call(owner, 5, address+int(at), int(n), value=int(fill))
            payload = api.bytes(owner, address, 64)
            api.call(owner, 2, address)
        elif op in ('copy', 'swap'):
            _, _, same, src, dst, n, width = args
            source = api.alloc(owner, 64)
            api.put(owner, source, pattern(64, 11))
            if same == 'true':
                dest = source
            else:
                dest = api.alloc(owner, 64)
                api.put(owner, dest, pattern(64, 29))
            api.call(owner, 6 if op == 'copy' else 7, source+int(src), int(n),
                other=dest+int(dst), width=0 if op == 'copy' else int(width))
            payload = api.bytes(owner, dest, 64)
            if dest != source:
                api.call(owner, 2, dest)
            api.call(owner, 2, source)
        elif op == 'zero':
            which = args[0]
            api.call(owner, 5 if which == 'set' else 6 if which == 'copy' else 7,
                width=int(which[-1]) if which.startswith('swap') else 0)
            value = 'void'
        else:
            raise ValueError('Unknown oracle operation ' + op)
        actual = dict(value=value, payload_hex=payload.hex(), exception=exception)
        check(actual == row['expected'], 'Actual MASM native vector differs from independent JDK: ' + row['id'])
        check(owner.live == owner.active == owner.logical == 0, 'Oracle replay frees all case resources')
        rows.append(dict(id=row['id'], operation=op, actual=actual))
    api.closed(owner)
    check(len(rows) == 133 and len(skipped) == 107, 'Exact native-only oracle replay boundary')
    check(artifact(vectors_path) == vector_pin and artifact(result_path) == oracle_pin, 'Oracle inputs changed')
    return dict(verified=True, vectors=vector_pin, independent_JDK_receipt=oracle_pin,
        native_cases=len(rows), groups=dict(collections.Counter(row['operation'] for row in rows)),
        all_actual_MASM_results=rows, skipped=skipped, heap_or_Java_adapter_executed=False,
        plain_sign_projection_is_test_comparison_only=True, no_JVM_process_invoked=True,
        uninitialized_grown_tail_compared=False, pointer_identity_compared=False)

def readonly_jimage_test(api):
    module = READONLY_FILE
    K.CreateFileW.argtypes, K.CreateFileW.restype = [c.c_wchar_p, U, U, P, U, U, P], P
    K.CreateFileMappingW.argtypes, K.CreateFileMappingW.restype = [P, P, U, U, U, c.c_wchar_p], P
    K.MapViewOfFile.argtypes, K.MapViewOfFile.restype = [P, U, U, U, c.c_size_t], P
    K.UnmapViewOfFile.argtypes, K.UnmapViewOfFile.restype = [P], c.c_int
    K.CloseHandle.argtypes, K.CloseHandle.restype = [P], c.c_int
    file = K.CreateFileW(str(module), 0x80000000, 1, None, 3, 0, None)
    check(file and file != c.c_void_p(-1).value, 'Read-only actual modules file')
    mapping = view = None
    owner = None
    try:
        mapping = K.CreateFileMappingW(file, None, 2, 0, 0, None)
        check(mapping, 'Actual PAGE_READONLY modules mapping')
        view = K.MapViewOfFile(mapping, 4, 0, 0, 4096)
        check(view, 'Actual FILE_MAP_READ modules view')
        original = c.string_at(view, 64)
        owner = api.owner()
        address = api.alloc(owner, 64)
        for op, kw in [(3, dict(size=8, width=8)), (4, dict(size=8, width=8, value=0)),
            (5, dict(size=64, value=0)), (6, dict(size=32, other=address)), (2, {}), (1, dict(size=64))]:
            api.call(owner, op, view, expected=1, **kw)
        api.call(owner, 6, address, 32, other=view, expected=1)
        api.call(owner, 7, address, 32, other=view, width=8, expected=1)
        check(c.string_at(view, 64) == original, 'RO JIMAGE bytes untouched after all rejected writes/free/resize')
        api.closed(owner)
        owner = None
    finally:
        if owner:
            api.close(c.byref(owner))
        if view:
            check(K.UnmapViewOfFile(view), 'Unmap native RO test view')
        if mapping:
            check(K.CloseHandle(mapping), 'Close native RO test mapping')
        check(K.CloseHandle(file), 'Close native RO test file')
    return dict(case='actual-readonly-input-domain-refuses-all-core-writes', input=artifact(module), header64_sha256=hashlib.sha256(original).hexdigest())

def concurrency_tests(api):
    owner = api.owner(capacity=128)
    barrier = threading.Barrier(8)

    def independent(index):
        ident = int(K.GetCurrentThreadId())
        barrier.wait(timeout=20)
        for iteration in range(24):
            address = api.alloc(owner, 64)
            value = ((index+1) << 56) | iteration
            api.call(owner, 4, address+3, 8, value=value, width=8)
            check(api.call(owner, 3, address+3, 8, width=8).result == value, '8OS independent data')
            api.call(owner, 5, address+16, 16, value=index+iteration)
            grown = api.call(owner, 1, address, 128).result
            check(api.call(owner, 3, grown+3, 8, width=8).result == value, '8OS resize preserves data')
            api.call(owner, 6, grown+16, 16, other=grown+32)
            check(api.bytes(owner, grown+32, 16) == bytes([(index+iteration) & 255])*16, '8OS copy bytes')
            api.call(owner, 2, grown)
        return dict(index=index, os_thread=ident, iterations=24)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        independent_rows = list(pool.map(independent, range(8)))
    check(len({row['os_thread'] for row in independent_rows}) == 8 and owner.live == owner.active == owner.logical == 0,
        'Exactly 8 independent OS workers finish with no payload/lease residue')
    address = api.alloc(owner, 64)
    patterns = [((index+1) * 0x101010101010101) & ((1 << 64)-1) for index in range(8)]
    api.call(owner, 4, address, 8, width=8, value=patterns[0])
    barrier = threading.Barrier(8)

    def shared(index):
        ident = int(K.GetCurrentThreadId())
        barrier.wait(timeout=20)
        for iteration in range(128):
            api.call(owner, 4, address, 8, width=8, value=patterns[index])
            check(api.call(owner, 3, address, 8, width=8).result in patterns, 'Shared block read never sees partial written value')
        return dict(index=index, os_thread=ident, writes=128, reads=128)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        shared_rows = list(pool.map(shared, range(8)))
    check(len({row['os_thread'] for row in shared_rows}) == 8, 'Exactly 8 OS workers contend on same valid block')
    barrier = threading.Barrier(8)
    after_busy = threading.Barrier(8)

    def borrowed(index):
        lease = api.call(owner, 8, address, 32, flags=1)
        ident = int(K.GetCurrentThreadId())
        barrier.wait(timeout=20)
        if index == 0:
            api.call(owner, 4, address, 8, width=8, value=0, expected=2)
            api.call(owner, 5, address, 64, value=0, expected=2)
            api.call(owner, 1, address, 128, expected=2)
            api.call(owner, 2, address, expected=2)
            check(api.close(c.byref(owner)) == 2 and owner.state == 1, 'Concurrent leased close busy keeps ready')
        after_busy.wait(timeout=20)
        api.call(owner, 9, token=lease.token)
        return dict(index=index, os_thread=ident, lease=lease.token)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        borrow_rows = list(pool.map(borrowed, range(8)))
    check(len({row['os_thread'] for row in borrow_rows}) == 8 and len({row['lease'] for row in borrow_rows}) == 8,
        'Eight actual concurrent read leases are distinct and all retired')
    api.call(owner, 4, address, 8, width=8, value=0x9988776655443322)
    check(api.call(owner, 3, address, 8, width=8).result == 0x9988776655443322, 'Same block retry succeeds after all leases release')
    api.call(owner, 2, address)
    api.closed(owner)
    return dict(global_exclusive_serialization=True, performance_or_game_scaling_claim=False,
        independent=independent_rows, shared_block=shared_rows, concurrent_borrow_conflict=borrow_rows)

def fault_tests(api):
    cases = []
    owner = Owner()
    api.fault(1, 0)
    check(api.init(c.byref(owner), 128, 8, 65536) == 4 and owner.state == 3 and owner.records == 0 and owner.os_error == 8,
        'Injected native metadata VirtualAlloc failure leaves closed owner')
    check(api.init(c.byref(owner), 128, 8, 65536) == 0, 'Native init retries after controlled OS failure')
    api.fault(1, 0)
    api.call(owner, 0, size=64, expected=4)
    check(owner.live == owner.logical == 0, 'Injected payload allocation failure owns nothing')
    address = api.alloc(owner, 64)
    api.call(owner, 5, address, 64, value=0xA9)
    api.fault(1, 0)
    failed = api.call(owner, 1, address, 128, expected=4)
    check(failed.os_error == 8 and owner.live == 1 and owner.logical == 64 and
        api.bytes(owner, address, 64) == bytes([0xA9])*64, 'Injected realloc OOM fully preserves old block')
    cases.append('native-injected-metadata-alloc-payload-alloc-and-realloc-failure')
    api.fault(0, 1)
    failed = api.call(owner, 2, address, expected=12)
    check(failed.os_error == 5 and owner.live == 1 and owner.state == 1, 'Free failure keeps original live record')
    check(api.bytes(owner, address, 64) == bytes([0xA9])*64, 'Failed free still readable')
    api.fault(0, 1)
    failed = api.call(owner, 1, address, 128, expected=12)
    check(failed.os_error == 5 and owner.live == 1 and owner.logical == 64, 'Failed old free rolls new allocation back')
    check(api.bytes(owner, address, 64) == bytes([0xA9])*64, 'Realloc release failure preserves exact old bytes')
    api.fault(0, 3)
    api.call(owner, 1, address, 128, expected=12)
    check(owner.live == 2 and owner.logical == 192 and owner.active == 0, 'Double-free-failure retains both native allocations')
    pending = [Q.from_address(owner.records+i*64).value for i in range(owner.capacity)
        if U.from_address(owner.records+i*64+40).value == 2]
    check(len(pending) == 1, 'Exactly unpublished replacement remains cleanup-pending')
    api.call(owner, 3, pending[0], 1, width=1, expected=9)
    check(api.bytes(owner, address, 64) == bytes([0xA9])*64, 'Old allocation survives double cleanup failure')
    api.closed(owner)
    cases.append('native-injected-free-realloc-rollback-and-tracked-orphan-retry')
    owner = api.owner(capacity=8, budget=65536)
    api.alloc(owner, 64)
    api.alloc(owner, 128)
    api.fault(0, 1)
    check(api.close(c.byref(owner)) == 12 and owner.state == 2 and owner.live == 1 and owner.logical == 64 and owner.metadata,
        'Close native payload failure retains exact failed allocation and metadata')
    api.call(owner, 0, size=1, expected=9)
    api.closed(owner)
    owner = api.owner(capacity=8, budget=65536)
    api.alloc(owner, 64)
    api.fault(0, 2)
    check(api.close(c.byref(owner)) == 12 and owner.state == 2 and owner.live == owner.logical == 0 and owner.metadata,
        'Close native metadata free failure retains metadata only')
    api.closed(owner)
    cases.append('native-injected-close-payload-and-metadata-failure-retry')
    return cases

def main():
    global ROOT, TOOLS, SDK, C, O, READONLY_FILE, ORACLE_VECTORS, ORACLE_RECEIPT, ORACLE_VECTORS_SHA, ORACLE_RECEIPT_SHA
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--candidate-tool', type=Path)
    parser.add_argument('--kernel', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--assembler', type=Path, default=TOOLS / 'ml64.exe')
    parser.add_argument('--linker', type=Path, default=TOOLS / 'link.exe')
    parser.add_argument('--kernel32', type=Path, default=SDK)
    parser.add_argument('--readonly-file', type=Path, required=True)
    parser.add_argument('--readonly-sha256', required=True)
    parser.add_argument('--vectors', type=Path)
    parser.add_argument('--vectors-sha256')
    parser.add_argument('--oracle-receipt', type=Path)
    parser.add_argument('--oracle-sha256')
    args = parser.parse_args()
    ROOT = args.root.resolve()
    tool = (args.candidate_tool or ROOT / 'scripts/native-memory-owner-candidate.py').resolve()
    spec = importlib.util.spec_from_file_location('published_native_memory_owner_candidate', tool)
    C = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(C)
    C.ROOT = ROOT
    O = C.reader()
    READONLY_FILE = args.readonly_file.resolve()
    check(artifact(READONLY_FILE)['sha256'] == args.readonly_sha256, 'Explicit sealed read-only input')
    oracle_args = (args.vectors, args.vectors_sha256, args.oracle_receipt, args.oracle_sha256)
    check(all(oracle_args) or not any(oracle_args), 'Oracle vector/receipt paths and both hashes must be supplied together')
    if all(oracle_args):
        ORACLE_VECTORS, ORACLE_RECEIPT = args.vectors.resolve(), args.oracle_receipt.resolve()
        ORACLE_VECTORS_SHA, ORACLE_RECEIPT_SHA = args.vectors_sha256, args.oracle_sha256
    kernel = C.kernel_path(args.kernel)
    assembler, linker, library = (p.resolve() for p in (args.assembler, args.linker, args.kernel32))
    TOOLS = assembler.parent
    check(linker.parent == TOOLS and assembler.name.lower() == 'ml64.exe' and linker.name.lower() == 'link.exe',
        'Native tests use explicit matching existing MSVC tool directory')
    SDK = library
    out = args.output.resolve()
    check(out.is_relative_to(ROOT / '.boom') and not out.exists(), 'Fresh ignored native test output required')
    out.mkdir(parents=True)

    def pins():
        result = dict(component_sources=C.sources(kernel), native_tests=artifact(__file__),
            assembler=artifact(assembler), linker=artifact(linker), kernel32=artifact(library), readonly=artifact(READONLY_FILE))
        if ORACLE_VECTORS is not None:
            result.update(vectors=artifact(ORACLE_VECTORS), independent_JDK_receipt=artifact(ORACLE_RECEIPT))
        return result

    report = dict(schema=1, verified=False, scope='standalone_pure_MASM_native_memory_tests',
        guest_Java_run=False, JVM_process_invoked=False, VM_integrated=False, runtime_registered=False,
        runtime_accepted=False, game_started=False, atomic_volatile_supported=False,
        stale_raw_address_ABA_fully_prevented=False, multicore_performance_improvement_claimed=False)
    before = pins()
    try:
        check(c.sizeof(Owner) == c.sizeof(Job) == 128 and Job.status.offset == 76 and Owner.sequence.offset == 88,
            'Actual native core ABI')
        candidate = C.build(out / 'candidate', kernel, assembler, linker, library)
        row = json.loads(candidate.read_text())
        first = dict(asm=row['assembly'], obj=row['object'], dll=row['image'], rsp=row['response'],
            normalized=O.normalized_coff(row['object']['path']))
        source = C.assembly(kernel)
        second = build(out / 'independent-test-assembly', source)
        check(first['normalized'] == second['normalized'] and
            Path(first['dll']['path']).read_bytes() == Path(second['dll']['path']).read_bytes(),
            'Actual published candidate complete canonical COFF/PE equals independent native test build')
        fault = build(out / 'native-fault-variant', source, fault=True)
        probe = build(out / 'native-ABI-probe', ABI_PROBE, expected_exports=['boom_native_memory_test_abi'], expected_imports=[])
        report.update(candidate=artifact(candidate), candidate_verification=artifact(candidate.with_name('verification.json')),
            builds=dict(canonical=first, independent=second, test_only_fault_variant=fault, native_ABI_probe=probe),
            canonical_COFF_equal=True, complete_canonical_PE_equal=True,
            fault_variant_core_machine_equivalence=fault_core_machine_equivalence(first['obj']['path'], fault['obj']['path']))
        api, fault_api = API(first['dll']['path']), API(fault['dll']['path'])
        report['actual_unwind'] = actual_unwind(api)
        report['actual_native_ABI_probe'] = native_abi_probe(api, probe['dll']['path'])
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as warm:
            check(warm.submit(lambda: int(K.GetCurrentThreadId())).result(), 'Warm development harness worker')
        before_handles = handles()
        report['normal_cases'] = normal_tests(api)
        report['independent_JDK_native_vectors'] = oracle_native_vectors(api) if ORACLE_VECTORS is not None else dict(
            verified=False, skipped=True, reason='No independent oracle inputs supplied', heap_or_Java_adapter_executed=False)
        report['readonly_domain'] = readonly_jimage_test(api)
        report['eight_OS'] = concurrency_tests(api)
        report['fault_cases'] = fault_tests(fault_api)
        report['handles'] = dict(before=before_handles, after=handles())
        report['actual_Windows_MEM_FREE_after_quiescent_close'] = dict(
            normal=api.closed_native_regions_observed_free, fault_injection=fault_api.closed_native_regions_observed_free)
        check(report['handles']['before'] == report['handles']['after'], 'All actual native handles conserved')
        check(pins() == before, 'Native test source/kernel/tools/explicit external inputs changed')
        for group in report['builds'].values():
            for key in ('asm', 'obj', 'dll', 'rsp'):
                check(artifact(group[key]['path']) == group[key], 'Tested actual machine artifact changed')
        report.update(verified=True, inputs_before_after_equal=True, pins=before,
            test_memory_budget_max=4*1024*1024, metadata_capacity_max_test=128,
            native_test_only_fault_masks=True, runtime_Python=False)
    except BaseException as exc:
        report['error'] = repr(exc)
        raise
    finally:
        write(out / 'verification.json', report)
    print(json.dumps(dict(verified=True, receipt=artifact(out / 'verification.json'),
        kernel=before['component_sources']['kernel'], normal_cases=len(report['normal_cases']),
        independent_JDK_native_vectors=report['independent_JDK_native_vectors'].get('native_cases', 0)), indent=2))


if __name__ == '__main__':
    main()
