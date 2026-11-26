"""Bind intact original System.initPhase3 to an ordered native process owner."""
import hashlib


REPORT_BYTES = 544
REPORT_ABI = 13
REPORT_FIELDS = dict(called=512, returned=516, VM_before=520, VM_after=524,
                     main_kind=528, main_pc=532, main_method=536, main_depth=540)


def contract(summary, owner, S, reader):
    origin = owner['origin']
    S.check(owner['name'] == 'java/lang/System' and owner['access'] == 0x31 and
            (origin['loader'], origin['source_id']) == ('bootstrap', 'jdk:java.base') and
            not origin.get('generated'), 'System phase 3 requires original final bootstrap System')
    original = S.original_class(summary, owner)
    name, methods = reader.original_methods(original)
    S.check(name == owner['name'] and len(methods) == len(owner['method_ids']), 'Original System method inventory differs')
    [(ident, method)] = [(i, m) for i, m in zip(owner['method_ids'], methods)
                        if (m['name'], m['descriptor'], m['access']) == ('initPhase3', '()V', 0x0a)]
    S.check(method['code'] is not None, 'Original private static System.initPhase3 Code is missing')
    body = method['code'][0]
    I = S.module('phase3_original_instruction_model', 'verify-translation-ir.py')
    parsed = I.Source(original)
    [source_method] = [m for m in parsed.methods if (m['name'], m['descriptor'], m['access']) == ('initPhase3', '()V', 0x0a)]
    source_code = parsed.code(source_method)
    S.check(source_code['bytes'] == body, 'Independent original Phase3 Code parsers differ')
    instructions = list(I.stream(body))
    calls, literals, transitions = [], [], []
    for at, instruction in enumerate(instructions):
        opcode = instruction['opcode']
        if opcode in (0xb6, 0xb7, 0xb8):
            member = parsed.member(instruction['operand']['Constant'])
            calls.append(dict(pc=instruction['pc'], opcode=opcode, **member))
            if (member['owner'], member['name'], member['descriptor']) == ('jdk/internal/misc/VM', 'initLevel', '(I)V'):
                S.check(at > 0 and 2 <= instructions[at-1]['opcode'] <= 8,
                        'Phase3 VM levels must remain original constant Java arguments')
                transitions.append(dict(pc=instruction['pc'], value=instructions[at-1]['opcode']-3))
        if opcode in (0x12, 0x13):
            tag, value = parsed.cp[instruction['operand']['Constant']]
            if tag in (7, 8):literals.append(dict(pc=instruction['pc'], kind='Class' if tag == 7 else 'String', value=parsed.text(value)))
    def call(owner_name, method_name, descriptor):
        matches = [c for c in calls if (c['owner'], c['name'], c['descriptor']) == (owner_name, method_name, descriptor)]
        S.check(len(matches) == 1, 'Original Phase3 lifecycle call missing or duplicated: '+method_name)
        return matches[0]
    loader = call('java/lang/ClassLoader', 'initSystemClassLoader', '()Ljava/lang/ClassLoader;')
    current = call('java/lang/Thread', 'currentThread', '()Ljava/lang/Thread;')
    context = call('java/lang/Thread', 'setContextClassLoader', '(Ljava/lang/ClassLoader;)V')
    ensure = call('jdk/internal/misc/Unsafe', 'ensureClassInitialized', '(Ljava/lang/Class;)V')
    factory = [c for c in literals if c['kind'] == 'Class' and c['value'] == 'java/lang/invoke/StringConcatFactory']
    S.check(len(factory) == 1 and factory[0]['pc'] < ensure['pc'] < loader['pc'] and
            [t['value'] for t in transitions] == [3, 4] and
            transitions[0]['pc'] < loader['pc'] < current['pc'] < context['pc'] < transitions[1]['pc'] and
            instructions[-1]['opcode'] == 0xb1 and instructions[-2]['pc'] == transitions[-1]['pc'] and
            [i['pc'] for i in instructions if i['opcode'] == 0xb1] == [instructions[-1]['pc']],
            'Original Phase3 initialization order or final normal return changed')
    S.check(any(c['kind'] == 'String' and c['value'] == 'java.security.manager' for c in literals),
            'Original security-manager property branch must remain part of Phase3')
    return dict(method=ident, symbol=f'boom_m{ident}', class_id=owner['id'], descriptor='()V',
        code_sha256=hashlib.sha256(body).hexdigest(), class_sha256=origin['sha256'], code_bytes=len(body),
        initial_VM_level=2, success_VM_level=4, original_VM_level_calls=transitions,
        source_calls=calls, source_literals=literals, source_exception_handlers=source_code['handlers'],
        report_bytes=REPORT_BYTES, report_abi=REPORT_ABI, report_fields=dict(REPORT_FIELDS),
        source_method_roots=[ident], source_initializer_dependencies=['java/lang/invoke/StringConcatFactory'],
        original_security_property_branches_preserved=True, ASM_writes_Java_state=False,
        ASM_sets_VM_level=False, full_game_startup_claimed=False)


def bind(closure, summary, owner, S, reader):
    model = contract(summary, owner, S, reader)
    selected = closure['selected_methods'].get(str(model['method']))
    S.check(selected is not None and selected['class_id'] == owner['id'] and
            (selected['name'], selected['descriptor'], selected['code_sha256'], selected['source_sha256']) ==
            ('initPhase3', '()V', model['code_sha256'], owner['origin']['sha256']),
            'Original System.initPhase3 must be selected intact before native ownership')
    return model
