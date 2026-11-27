"""Complete COFF comparison for canonical, entirely leaf diagnostic stops.

This is a narrow domain adapter for the unchanged owner COFF reader, not a
general native verifier. Callers must independently prove that the assembly
is the original sealed diagnostic source with only the declared complete
fail-only procedures removed. They must assemble that exact source anew and
compare it with the actual object using ``verify``. Native providers and
Frame8 adapters continue to require the original unwind checks.
"""
import ast
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import re
import struct

import capstone
from capstone.x86_const import X86_INS_RET, X86_OP_IMM, X86_OP_MEM

ROOT = Path(__file__).resolve().parents[1]
READER = ROOT / 'scripts/jimage-owner-candidate.py'
OWNER_READER_SHA256 = 'ed0a4c95a7e0027bd51be9435e87ea6eba6eb85724f7b105acaed3db7de07048'
OWNER_READER_AST_SHA256 = 'd0320233a912a168931af78130ba23f31426afdb58257fb9eaf58ea30a37b101'
UNWIND_CHECK = 'Missing/incomplete owner native x64 unwind table'
STACK_REGISTERS = {'rsp', 'esp', 'sp', 'spl', 'rbp', 'ebp', 'bp', 'bpl'}
NONVOLATILE = re.compile(r'(?:rbx|ebx|bx|bl|bh|rsi|esi|si|sil|rdi|edi|di|dil|rbp|ebp|bp|bpl|r1[2-5](?:[bdw])?|(?:xmm|ymm|zmm)(?:[6-9]|1[0-5]))')
RELOCATION_WIDTHS = {1: 8, 2: 4, 3: 4, 4: 4, 5: 4, 6: 4, 7: 4, 8: 4, 9: 4, 10: 2, 11: 4}


def check(value, message):
    if not value:
        raise ValueError(message)


def artifact(path):
    path = Path(path).resolve()
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(path=str(path), size=path.stat().st_size, sha256=digest)


def _reader():
    check(artifact(READER)['sha256'] == OWNER_READER_SHA256,
          'Locked complete owner reader source changed')
    spec = importlib.util.spec_from_file_location('diagnostic_leaf_original_owner', READER)
    owner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owner)
    tree = ast.parse(inspect.getsource(owner.normalized_coff))
    function = tree.body[0]
    original = ast.dump(function, include_attributes=False)
    check(hashlib.sha256(original.encode()).hexdigest() == OWNER_READER_AST_SHA256,
          'Locked complete owner reader AST changed')
    indices = [i for i, node in enumerate(function.body)
               if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
               and isinstance(node.value.func, ast.Name) and node.value.func.id == 'check'
               and len(node.value.args) == 2 and isinstance(node.value.args[1], ast.Constant)
               and node.value.args[1].value == UNWIND_CHECK]
    check(len(indices) == 1 and indices[0] == len(function.body) - 2,
          'Only the final owner-specific unwind requirement may be adapted')
    del function.body[indices[0]]
    ast.fix_missing_locations(tree)
    # This private namespace never changes the owner's globals or check().
    namespace = dict(owner.__dict__)
    exec(compile(tree, '<complete_reader_pure_leaf_diagnostic_domain>', 'exec'), namespace)
    return namespace['normalized_coff'], original


def leaf_stop_coff(path, source_bytes):
    """Return the complete normalized COFF and an exhaustive leaf-domain proof.

    ``source_bytes`` must be the exact canonical MASM bytes, not decoded and
    newline-normalized text. This function proves the restricted reader domain;
    only ``verify`` also proves actual/canonical machine equivalence.
    """
    check(isinstance(source_bytes, bytes), 'Exact canonical source bytes required')
    source = source_bytes.decode('utf-8')
    check(not re.search(r'(?mi)^\s*(?:\w+\s+PROC\s+FRAME|\.(?:pushreg|allocstack|savexmm128)|call\b|push\b|pop\b|enter\b|leave\b)', source),
          'Only canonical entirely leaf diagnostic sources may use this adapter')
    reader, original = _reader()
    normalized = reader(path)
    check('.pdata' not in normalized['sections'] and '.xdata' not in normalized['sections'],
          'Leaf-only adapter cannot replace a native/adapter unwind verifier')
    check(not normalized['imports'], 'Canonical leaf diagnostic code cannot import a call or jump target')
    raw = Path(path).read_bytes()
    count = struct.unpack_from('<H', raw, 2)[0]
    decoder = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    decoder.detail = True
    instructions = code_bytes = jumps = 0
    for index in range(count):
        at = 20 + 40 * index
        section_name = raw[at:at + 8].rstrip(b'\0').decode('ascii')
        length, offset = struct.unpack_from('<II', raw, at + 16)
        flags = struct.unpack_from('<I', raw, at + 36)[0]
        if not flags & 0x20000020:
            continue
        check(section_name in ('.text', '.text$mn') and flags & 0x20000000 and flags & 0x20,
              'Unexpected executable diagnostic section')
        data = raw[offset:offset + length]
        relocation_at, _, relocation_count = struct.unpack_from('<IIH', raw, at + 24)
        if flags & 0x01000000:
            relocation_count = struct.unpack_from('<I', raw, relocation_at)[0] - 1
            relocation_at += 10
        # The unchanged complete reader has already validated ordering, kinds,
        # widths and bounds. This domain additionally requires every branch to
        # be fully resolved within its code section before linking. A raw disp0
        # can otherwise appear local while its relocation actually targets data.
        relocation_ranges = []
        for reloc_index in range(relocation_count):
            begin, _, kind = struct.unpack_from('<IIH', raw, relocation_at + 10 * reloc_index)
            relocation_ranges.append((begin, begin + RELOCATION_WIDTHS[kind]))
        relocation_cursor = 0
        covered = 0
        boundaries = set()
        destinations = []
        for instruction in decoder.disasm(data, 0):
            check(instruction.address == covered
                  and not instruction.group(capstone.CS_GRP_CALL)
                  and not instruction.group(capstone.CS_GRP_INT)
                  and not instruction.group(capstone.CS_GRP_IRET)
                  and not instruction.group(capstone.CS_GRP_PRIVILEGE)
                  and not instruction.mnemonic.startswith(('push', 'pop', 'enter', 'leave', 'iret')),
                  'Diagnostic machine code is not entirely no-call leaf code')
            if instruction.group(capstone.CS_GRP_RET):
                check(instruction.id == X86_INS_RET and not instruction.operands,
                      'Leaf diagnostic return must be plain RET without operands')
            _, writes = instruction.regs_access()
            for register in writes:
                name = instruction.reg_name(register)
                if name in STACK_REGISTERS:
                    check(name == 'rsp' and instruction.id == X86_INS_RET and not instruction.operands,
                          'A nonleaf stack adjustment was introduced')
                check(not NONVOLATILE.fullmatch(name),
                      'A nonvolatile register needs unwind information')
            for operand in instruction.operands:
                if operand.type == X86_OP_MEM:
                    check(instruction.reg_name(operand.mem.base) not in STACK_REGISTERS
                          and instruction.reg_name(operand.mem.index) not in STACK_REGISTERS,
                          'Leaf diagnostic code cannot access stack memory')
            if instruction.group(capstone.CS_GRP_JUMP) or instruction.group(capstone.CS_GRP_BRANCH_RELATIVE):
                check(len(instruction.operands) == 1 and instruction.operands[0].type == X86_OP_IMM,
                      'Leaf diagnostic jumps must be local direct branches')
                while relocation_cursor < len(relocation_ranges) and relocation_ranges[relocation_cursor][1] <= instruction.address:
                    relocation_cursor += 1
                check(relocation_cursor == len(relocation_ranges)
                      or relocation_ranges[relocation_cursor][0] >= instruction.address + instruction.size,
                      'Leaf diagnostic branch bytes cannot be modified by a relocation')
                destinations.append(instruction.operands[0].imm)
            boundaries.add(instruction.address)
            covered += instruction.size
            instructions += 1
        check(covered == len(data), 'Leaf diagnostic code was not exhaustively decoded')
        check(all(destination in boundaries for destination in destinations),
              'Leaf diagnostic branch leaves its section or an instruction boundary')
        code_bytes += covered
        jumps += len(destinations)
    check(code_bytes and instructions, 'Actual diagnostic leaf code missing')
    return normalized, dict(
        scope='all_leaf_diagnostic_only_not_a_general_unwind_relaxation',
        complete_reader=artifact(READER), original_reader_AST_sha256=hashlib.sha256(original.encode()).hexdigest(),
        only_removed_check='final owner-specific pdata/xdata requirement',
        all_other_complete_reader_AST_unchanged=True,
        exhaustive_code_bytes=code_bytes, exhaustive_instructions=instructions, local_direct_jumps=jumps,
        no_calls_or_stack_access_or_adjustments_or_nonvolatile_writes=True,
        no_imports_and_all_branches_on_local_instruction_boundaries=True,
        only_plain_returns_and_no_relocations_overlapping_branch_bytes=True,
        capstone_source=artifact(Path(capstone.__file__)),
        source_sha256=hashlib.sha256(source_bytes).hexdigest())


def verify(actual_object, canonical_object, source_bytes):
    """Require complete actual/canonical equivalence in the proven leaf domain.

    The caller owns fresh canonical assembly and its exact source derivation.
    No original source verification or native-provider acceptance is implied.
    """
    actual, actual_leaf = leaf_stop_coff(actual_object, source_bytes)
    canonical, canonical_leaf = leaf_stop_coff(canonical_object, source_bytes)
    check(actual == canonical,
          'Actual leaf diagnostic COFF code/data/flags/symbols/aux/relocations differs')
    return dict(verified=True, scope='complete_pure_leaf_diagnostic_COFF_only',
                actual=artifact(actual_object), canonical=artifact(canonical_object),
                actual_leaf=actual_leaf, canonical_leaf=canonical_leaf,
                helper=artifact(__file__),
                normalized_sha256=hashlib.sha256(json.dumps(actual, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                full_source_selection_reverified=False, native_provider_unwind_policy_changed=False)
