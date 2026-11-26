"""Source and report contracts for the module-system phase of native VM startup."""
import hashlib


def bind(closure, summary, owner, S, reader):
    origin = owner['origin']
    S.check(owner['name'] == 'java/lang/System' and owner['access'] == 0x31 and
            (origin['loader'], origin['source_id']) == ('bootstrap', 'jdk:java.base') and not origin.get('generated'),
            'System phase 2 needs original final bootstrap System')
    name, methods = reader.original_methods(S.original_class(summary, owner))
    S.check(name == owner['name'] and len(methods) == len(owner['method_ids']), 'System class inventory differs')
    matches = [(i, m) for i, m in zip(owner['method_ids'], methods) if
               (m['name'], m['descriptor'], m['access']) == ('initPhase2', '(ZZ)I', 0x0a)]
    S.check(len(matches) == 1 and matches[0][1]['code'] is not None, 'Private static System.initPhase2 code missing')
    i, m = matches[0]
    code_hash = hashlib.sha256(m['code'][0]).hexdigest()
    selected = closure['selected_methods'].get(str(i))
    S.check(selected is not None and selected['class_id'] == owner['id'] and
            (selected['name'], selected['descriptor'], selected['code_sha256'], selected['source_sha256']) ==
            ('initPhase2', '(ZZ)I', code_hash, origin['sha256']), 'Original System.initPhase2 must be selected intact')
    return dict(method=i, symbol=f'boom_m{i}', class_id=owner['id'], code_sha256=code_hash, class_sha256=origin['sha256'],
                print_to_stderr=True, print_stack_trace=False, initial_VM_level=1, success_VM_level=2)
