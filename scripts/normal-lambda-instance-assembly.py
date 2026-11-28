"""Public instance-reference lowering over the unchanged normal ASM backend.

This module renders source only. Public REF5/9 targets reuse a source-selected
ordinary dispatch thunk. No abstract declaration is turned into a Java body.
REF6 bodies are delegated byte-for-byte. Code PCs are read from the actual new
Class, including compact loads and the five-byte invokeinterface instruction.
"""
import copy
import hashlib
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


OLD = load('instance_asm_unchanged_original_renderer', ROOT/'scripts/normal-lambda-assembly.py')
C = load('instance_asm_unchanged_original_class_reader', ROOT/'scripts/normal-lambda-source.py')


def check(value, message):
    if not value:
        raise ValueError(message)


def original_dispatch(plan, selection, available_symbols):
    """Select only an already provided, exact original member dispatch recipe."""
    implementation = plan['implementation']
    member = plan['implementation_member']
    kind = implementation['reference_kind']
    opcode = {5: 182, 9: 185}.get(kind)
    check(opcode is not None, 'An ordinary public instance handle is required')
    ordinary = plan.get('ordinary_target', {})
    check(ordinary.get('CallerSensitive') is False and ordinary.get('signature_polymorphic') is False and
          ordinary.get('class_sha256') == member['class_sha256'],
          'Original ordinary-target annotation and declaration proof is required')
    candidates = []
    for row in selection['selected_dispatch_sites'].values():
        dispatch = row.get('dispatch') or {}
        if (row.get('opcode') != opcode or row.get('resolved_method') != member['method'] or
                row.get('descriptor') != implementation['descriptor'] or
                row.get('diagnostic') is not None or row.get('label') not in available_symbols):
            continue
        if (dispatch.get('symbolic_owner') != member['class_id'] or
                dispatch.get('receiver_constraint') != member['class_id'] or
                dispatch.get('resolved_owner') != member['class_id'] or
                dispatch.get('interface') is not (kind == 9)):
            continue
        table = selection['selected_dispatch_tables'].get(str(row['table']))
        check(table is not None and table['resolved_method'] == member['method'],
              'The original dispatch table does not bind the exact target member')
        candidates.append(row)
    check(candidates, 'No already linked source-selected dispatch for this instance target')
    chosen = min(candidates, key=lambda row: (row['caller_class'], row['constant'], row['label']))
    return dict(label=chosen['label'], site=copy.deepcopy(chosen),
                table=copy.deepcopy(selection['selected_dispatch_tables'][str(chosen['table'])]),
                abstract_declaration_called_directly=False,
                declaring_owner_initialization_requested=False)


def actual_sam(g):
    file = g['class_file']
    blob = Path(file['path']).read_bytes()
    check(len(blob) == file['digest']['size'] and hashlib.sha256(blob).hexdigest() == file['digest']['sha256'],
          'The explicit generated Class bytes changed')
    raw = C.I.Source(blob)
    plan = g['contract']
    selected = [method for method in raw.methods if
                (method['name'], method['descriptor']) == (plan['sam_name'], plan['sam_descriptor'])]
    check(len(selected) == 1, 'One actual generated SAM declaration is required')
    code = raw.code(selected[0])['bytes']
    method = next(m for m in g['methods'] if m['name'] == plan['sam_name'])
    check(method['code_length'] == len(code) and method['code_sha256'] == hashlib.sha256(code).hexdigest(),
          'The generated SAM identity/Code map changed')
    operations = list(C.I.stream(code))
    invokes = [op for op in operations if op['opcode'] in (182, 185)]
    kind = plan['implementation']['reference_kind']
    check(len(invokes) == 1 and invokes[0]['opcode'] == {5: 182, 9: 185}[kind],
          'One actual matching virtual/interface instruction is required')
    pc = invokes[0]['pc']
    member = raw.member(int.from_bytes(code[pc+1:pc+3], 'big'))
    check({k: member[k] for k in ('owner', 'name', 'descriptor', 'interface')} ==
          {k: plan['implementation'][k] for k in ('owner', 'name', 'descriptor', 'interface')},
          'Actual Class invocation differs from the source contract')
    if kind == 9:
        args, _ = C.P.signature(member['descriptor'])
        check(code[pc+3:pc+5] == bytes([len(args)+1, 0]), 'Actual invokeinterface count/reserved bytes differ')
    return method, code, operations, pc


def pc_source(method_id, pc):
    return (f' mov DWORD PTR [rsp+280],{pc}\n'
            f' mov DWORD PTR [rbx+4],{pc}\n'
            f' mov DWORD PTR [rbx+8],{method_id}\n')


def body(g, sources, binding):
    plan = g['contract']
    kind = plan['implementation']['reference_kind']
    if kind == 6:
        check(binding is None, 'An original REF6 body must not receive a replacement binding')
        return OLD.body(g, sources), dict(original_REF6_body_byte_equal=True)
    check(kind in (5, 9) and binding and binding['site']['opcode'] == {5: 182, 9: 185}[kind],
          'An exact original ordinary instance dispatch binding is required')
    ordinary = plan.get('ordinary_target', {})
    check(ordinary.get('CallerSensitive') is False and ordinary.get('signature_polymorphic') is False and
          ordinary.get('class_sha256') == plan['implementation_member']['class_sha256'],
          'Special caller or polymorphic invocation semantics are outside this backend domain')
    check(binding['site']['resolved_method'] == plan['implementation_member']['method'] and
          binding['site']['descriptor'] == plan['implementation']['descriptor'],
          'Dispatch binding and original instance member differ')
    check(plan['invocation']['declaring_owner_initialization_requested'] is False and
          plan['invocation']['direct_declared_Java_body_required'] is False,
          'An instance invocation must not request a static declaration body or class initializer')
    method, code, operations, invoke_pc = actual_sam(g)
    method_id = method['id']
    original = OLD.body(g, sources)
    start_marker = f'boom_m{method_id}_body PROC FRAME\n'
    end_marker = f'boom_m{method_id}_body ENDP\n'
    check(original.count(start_marker) == original.count(end_marker) == 1,
          'The unchanged native template has no unique SAM body')
    start = original.index(start_marker)
    end = original.index(end_marker, start)+len(end_marker)
    sam = original[start:end]
    target = plan['implementation_member']
    before = f''' lea rcx,boom_class{target['class_id']}
 mov rdx,rbx
 call boom_class_ensure32
 cmp DWORD PTR [rbx],0
 jne lambda_m{method_id}_throw
 mov rcx,rbx
 lea rdx,[rsp+64]
 call boom_m{target['method']}
 cmp DWORD PTR [rbx],0
 jne lambda_m{method_id}_throw
'''
    after = f''' mov rcx,rbx
 lea rdx,[rsp+64]
 call {binding['label']}
 cmp DWORD PTR [rbx],0
 jne lambda_m{method_id}_throw
'''
    check(sam.count(before) == 1, 'The original static-call template scope differs')
    # Plan all edits in the unchanged text, then apply in reverse order so a
    # new PC can never be confused with another site's old PC.
    edits = [(sam.index(before), before, after, 'ordinary_instance_dispatch')]
    casts_before = [op['pc'] for op in operations if op['opcode'] == 192 and op['pc'] < invoke_pc]
    casts_after = [op['pc'] for op in operations if op['opcode'] == 192 and op['pc'] > invoke_pc]
    old_pc = 5*len(g['layout']['fields'])
    mapping = []
    wanted_before = sum(a != b for a, b in zip(plan['sam_arguments'], plan['instantiated_arguments']))
    check(len(casts_before) == wanted_before, 'The actual generated argument cast map differs')
    cast_index = 0
    for erased, instantiated in zip(plan['sam_arguments'], plan['instantiated_arguments']):
        old_pc += 2
        if erased != instantiated:
            mapping.append((old_pc, casts_before[cast_index], 'argument_checkcast'))
            cast_index += 1
            old_pc += 3
    mapping.append((old_pc, invoke_pc, 'instance_invoke'))
    result = plan['instantiated_result']
    result_cast = result.startswith(('L', '[')) and result != plan['implementation_result']
    check(len(casts_after) == int(result_cast), 'The actual generated result cast map differs')
    if result_cast:
        mapping.append((old_pc+3, casts_after[0], 'result_checkcast'))
    for old, new, label in mapping:
        prior, current = pc_source(method_id, old), pc_source(method_id, new)
        check(sam.count(prior) == 1, 'The original template PC range is ambiguous: '+label)
        if prior != current:
            edits.append((sam.index(prior), prior, current, label))
    edits.sort(key=lambda item: item[0])
    check(all(a[0]+len(a[1]) <= b[0] for a, b in zip(edits, edits[1:])), 'Native source edit scopes overlap')
    transformed = sam
    for at, prior, current, label in reversed(edits):
        check(transformed[at:at+len(prior)] == prior, 'Native source edit location differs: '+label)
        transformed = transformed[:at]+current+transformed[at+len(prior):]
    reconstructed = transformed
    delta = 0
    inverse = []
    for at, prior, current, label in edits:
        inverse.append((at+delta, current, prior, label))
        delta += len(current)-len(prior)
    for at, current, prior, label in reversed(inverse):
        check(reconstructed[at:at+len(current)] == current, 'Native source inverse scope differs: '+label)
        reconstructed = reconstructed[:at]+prior+reconstructed[at+len(current):]
    check(reconstructed == sam, 'The complete native SAM template inverse differs')
    text = original[:start]+transformed+original[end:]
    check(text[:start] == original[:start] and text.endswith(original[end:]),
          'The unchanged constructor/factory/data/epilogue complement differs')
    return text, dict(reference_kind=kind, target_original_dispatch=binding,
        original_template_sha256=hashlib.sha256(original.encode()).hexdigest(),
        source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        exact_native_template_inverse=True, edits=[dict(offset=at, before=prior, after=current, role=label)
                                                for at, prior, current, label in edits],
        actual_SAM_Code_sha256=hashlib.sha256(code).hexdigest(),
        actual_source_PC_mapping=[dict(template_pc=a, actual_pc=b, role=label) for a,b,label in mapping],
        original_Java_bodies_changed=False, abstract_declaration_body_used=False,
        source_only=True, assembled_or_executed=False)


def module(manifest, sources, dispatch_bindings):
    parts = ['.data?\nALIGN 8\nPUBLIC boom_lambda_failure_roots\nboom_lambda_failure_roots LABEL QWORD\n']
    proofs = []
    for generated in manifest['generated']:
        kind = generated['contract']['implementation']['reference_kind']
        binding = None if kind == 6 else dispatch_bindings.get(generated['contract']['binding_label'])
        text, proof = body(generated, sources, binding)
        parts.append(text)
        proofs.append(dict(type_id=generated['type_id'], **proof))
    parts.append(f'.const\nPUBLIC boom_lambda_failure_root_count\nboom_lambda_failure_root_count QWORD {len(manifest["generated"])}\n')
    return '\n'.join(parts), proofs
