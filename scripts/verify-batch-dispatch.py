"""Independently select source methods, check shared MASM tables and AMD64 COFF.

Does not execute Java or certify a whole-image runtime/launch. No native target
is accepted merely because a call adapter was generated.
"""
from collections import defaultdict
from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import re
import zipfile


def check(value, message):
    if not value: raise ValueError(message)


class Requests:
    def __init__(self, enable_array_clones=False, enable_classes=False, enable_concat=False):
        self.sites = {}
        self.gaps = {}
        self.constants = defaultdict(dict)
        self.emitted = set()
        self.array_clones = {} if enable_array_clones else None
        self.class_literals = {} if enable_classes else None
        self.concat_sites = {} if enable_concat else None

    def observe(self, class_id, sha, method_id, binding):
        check((binding['caller_class'], binding['caller_method']) == (class_id, method_id),
              'Binding caller identity differs')
        if binding['kind'] == 'string_literal_resolution': return
        self.constants[class_id][str(binding['constant'])] = None
        if self.concat_sites is not None and binding['kind']=='invokedynamic' and (binding.get('protocol') or '').startswith('java/lang/invoke/StringConcatFactory.'):
            site={k:binding[k] for k in ('label','caller_class','constant','opcode','descriptor')};site['class_sha256']=sha
            old=self.concat_sites.setdefault(binding['label'],dict(site=site,methods=set(),binding=binding))
            check(old['site']==site,'Conflicting concat source binding');old['methods'].add(method_id);return
        if binding['kind']=='literal_resolution' and binding.get('protocol')=='java/lang/Class' and self.class_literals is not None:
            check(isinstance(binding.get('literal_type'),int) and binding['opcode'] in (18,19),'Class literal lacks represented-type identity')
            site=dict(label=binding['label'],caller_class=class_id,class_sha256=sha,constant=binding['constant'],type_id=binding['literal_type'])
            old=self.class_literals.setdefault(binding['label'],dict(site=site,methods=set()))
            check(old['site']==site,'Conflicting source Class constant');old['methods'].add(method_id);return
        if binding['kind'] == 'array_clone' and self.array_clones is not None:
            site = {key: binding[key] for key in ('label','caller_class','constant','opcode','descriptor','array_type')}
            site['class_sha256'] = sha
            old = self.array_clones.setdefault(binding['label'], dict(site=site, methods=set()))
            check(old['site'] == site and binding['resolved_method'] is None, 'Conflicting source array clone binding')
            old['methods'].add(method_id)
            return
        if binding['kind'] == 'virtual_dispatch':
            site = dict(label=binding['label'], caller_class=class_id, class_sha256=sha,
                        constant=binding['constant'], opcode=binding['opcode'], descriptor=binding['descriptor'],
                        resolved_method=binding['resolved_method'], dispatch=binding['dispatch'])
            old = self.sites.setdefault(binding['label'], dict(site=site, methods=set()))
            check(old['site'] == site, 'Conflicting source virtual binding')
            old['methods'].add(method_id)
        else:
            protocol = ('native:' + str(binding['resolved_method']) if binding['kind'] == 'native_declaration'
                        else binding.get('protocol', binding['kind']))
            key = binding['kind'], protocol
            gap = self.gaps.setdefault(key, dict(symbols=set(), methods=set(), examples={}))
            gap['symbols'].add(binding['label']); gap['methods'].add(method_id)
            if len(gap['examples']) < 6: gap['examples'].setdefault(binding['label'], binding)


    def reject_concat(self,labels):
        for label in labels:
            item=self.concat_sites[label];binding=item['binding'];key=('invokedynamic',binding['protocol'])
            gap=self.gaps.setdefault(key,dict(symbols=set(),methods=set(),examples={}))
            gap['symbols'].add(label);gap['methods'].update(item['methods'])
            if len(gap['examples'])<6:gap['examples'].setdefault(label,binding)


class Model:
    def __init__(self, classes, inventory):
        spec = importlib.util.spec_from_file_location('dispatch_source_types', Path(__file__).with_name('verify-batch-metadata.py'))
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        self.classes, self.inventory = classes, inventory
        self.lookup, self.ancestry, self.parents, self.omitted = module.source_model(classes)
        self.methods = [dict() for _ in classes]
        self.indices = {}
        for id_, row in enumerate(inventory):
            owner, name, desc = row[:3]
            check((name, desc) not in self.methods[owner], 'Duplicate source method signature')
            self.methods[owner][name, desc] = id_
        for c in classes:
            for index, method in enumerate(c['method_ids']): self.indices[method] = index
        self.root = self.lookup('bootstrap', 'java/lang/Object')

    def access(self, method): return self.inventory[method][8]
    def owner(self, method): return self.inventory[method][0]

    def same_package(self, a, b):
        a, b = self.classes[a], self.classes[b]
        return (a['origin']['loader'], a['name'].rpartition('/')[0]) == (b['origin']['loader'], b['name'].rpartition('/')[0])

    @lru_cache(maxsize=None)
    def maximal(self, receiver, name, descriptor):
        candidates = [id_ for ancestor in self.ancestry[receiver] if ancestor != receiver
                      and self.classes[ancestor]['access'] & 0x200
                      if (id_ := self.methods[ancestor].get((name, descriptor))) is not None
                      and not self.access(id_) & (2 | 8)]
        return tuple(sorted((id_ for id_ in candidates if not any(
            self.owner(other) != self.owner(id_) and self.owner(id_) in self.ancestry[self.owner(other)]
            for other in candidates)), key=self.owner))

    def resolve(self, owner, name, desc, interface):
        check(bool(self.classes[owner]['access'] & 0x200) == interface, 'Source invocation owner kind differs')
        own = self.methods[owner].get((name, desc))
        if own is not None: return own
        if interface:
            own = self.methods[self.root].get((name, desc))
            if own is not None and self.access(own) & 9 == 1: return own
        else:
            parent = self.parents[owner]
            while parent is not None:
                own = self.methods[parent].get((name, desc))
                if own is not None: return own
                parent = self.parents[parent]
        maximal = self.maximal(owner, name, desc)
        concrete = [m for m in maximal if not self.access(m) & 0x400]
        check(bool(maximal), 'Missing source resolution target')
        return concrete[0] if len(concrete) == 1 else maximal[0]

    @lru_cache(maxsize=None)
    def overrides(self, candidate, resolved):
        ca, ra = self.access(candidate), self.access(resolved)
        if self.inventory[candidate][1:3] != self.inventory[resolved][1:3] or ca & (2 | 8) or ra & 8: return False
        if ra & 5 or self.same_package(self.owner(candidate), self.owner(resolved)): return not ra & 2
        if ra & 2: return False
        parent = self.parents[self.owner(candidate)]
        name, desc = self.inventory[candidate][1:3]
        while parent is not None and parent != self.owner(resolved):
            middle = self.methods[parent].get((name, desc))
            if middle is not None and self.overrides(candidate, middle) and self.overrides(middle, resolved): return True
            parent = self.parents[parent]
        return False

    def select(self, receiver, resolved, interface):
        flags = self.access(resolved); name, desc = self.inventory[resolved][1:3]
        chosen = resolved if flags & 2 else None
        current = receiver
        if chosen is None:
            while current is not None:
                candidate = self.methods[current].get((name, desc))
                if candidate is not None and self.overrides(candidate, resolved): chosen = candidate; break
                current = self.parents[current]
            if chosen is None:
                concrete = [m for m in self.maximal(receiver, name, desc) if not self.access(m) & 0x400]
                if len(concrete) > 1: return None, 13
                if concrete: chosen = concrete[0]
        if chosen is None or self.access(chosen) & 0x400: return None, 14
        if interface and not self.access(chosen) & 1 and not flags & 2: return None, 15
        return chosen, 0


def verify(root, batch, plan, inventory, requests, artifact, coff_symbols, file_digest, provided_natives=frozenset()):
    root, plan = Path(root), Path(plan); summary = batch['dispatch']
    requests.gaps={key:value for key,value in requests.gaps.items()
                   if not (key[0]=='native_declaration' and int(key[1].removeprefix('native:')) in provided_natives)}
    check((summary['abi'], summary['context_bytes']) == (1, 32), 'Invalid dispatch ABI')
    for flag in ('linked', 'runtime_abi_verified', 'game_started', 'class_initialization_performed_by_dispatch'):
        check(summary[flag] is False, 'Dispatch claims unverified runtime behavior')
    classes = list(map(json.loads, (plan/'classes.jsonl').read_text(encoding='utf-8').splitlines()))
    model = Model(classes, inventory)
    arrays = list(map(json.loads, artifact(root, batch['array_types']).read_text(encoding='utf-8').splitlines()))
    array_index = {(a['defining_loader'], a['descriptor']): a['id'] for a in arrays}
    with zipfile.ZipFile(artifact(root, summary['index'], 'dispatch')) as bundle:
        check(bundle.namelist() == ['sites.jsonl', 'tables.jsonl', 'targets.jsonl', 'gaps.jsonl'], 'Unexpected dispatch index')
        data = {name: list(map(json.loads, bundle.read(name).splitlines())) for name in bundle.namelist()}
    sites, tables, targets, gaps = [data[name] for name in ('sites.jsonl', 'tables.jsonl', 'targets.jsonl', 'gaps.jsonl')]
    check([s['label'] for s in sites] == sorted(requests.sites), 'Virtual site coverage differs')
    keys = sorted({(s['site']['resolved_method'], s['site']['dispatch']['interface']) for s in requests.sites.values()})
    check([(t['resolved_method'], t['interface']) for t in tables] == keys, 'Shared dispatch table coverage differs')
    check([t['id'] for t in tables] == list(range(len(tables))), 'Invalid dispatch table IDs')
    table_ids = {key: id_ for id_, key in enumerate(keys)}
    layouts = {r['class_id'] for r in map(json.loads, artifact(root, batch['layouts']).read_text(encoding='utf-8').splitlines())
               if r['candidate'] is not None}
    receivers = defaultdict(list)
    for c in classes:
        if c['id'] in layouts and not c['access'] & 0x200:
            for ancestor in model.ancestry[c['id']]: receivers[ancestor].append(c['id'])
    used_targets, expected_bodies, expected_defs = set(), defaultdict(list), defaultdict(set)
    kernel = Path(__file__).resolve().parents[1]/'native/kernels/batch_virtual_dispatch.inc'
    check(file_digest(kernel)['sha256'] == summary['kernel_sha256'], 'Dispatch kernel source changed')
    if tables:
        expected_bodies[0].append(kernel.read_text(encoding='utf-8'))
        expected_defs[0].add('boom_batch_virtual_invoke')
    for t in tables:
        method, interface = t['resolved_method'], t['interface']; owner = model.owner(method)
        expected = [dict(receiver=r, target=target, error=error) for r in receivers[owner]
                    for target, error in [model.select(r, method, interface)]]
        array_target = method if owner == model.root and not model.access(method) & (8 | 0x400) and (
            not interface or model.access(method) & 1) else None
        check(t['diagnostic'] is None and t['rows'] == expected, 'Dispatch selection differs from original source hierarchy')
        check((t['array_target'], t['array_error']) == (array_target, 0 if array_target is not None else 13), 'Array dispatch differs')
        check(isinstance(t['assembly_unit'], int), 'Missing generated dispatch table')
        id_ = t['id']; ptr = f'OFFSET boom_m{array_target}' if array_target is not None else '0'
        body = f".const\nALIGN 8\nPUBLIC boom_batch_vtable{id_}\nboom_batch_vtable{id_} DWORD 056445350h,1,{len(expected)},0\n QWORD OFFSET boom_batch_vrows{id_},{ptr}\n DWORD {t['array_error']},0\nboom_batch_vrows{id_} LABEL BYTE\n"
        for row in expected:
            ptr = f"OFFSET boom_m{row['target']}" if row['target'] is not None else '0'
            body += f" DWORD {row['receiver']},{row['error']}\n QWORD {ptr}\n"
            if row['target'] is not None: used_targets.add(row['target'])
        if array_target is not None: used_targets.add(array_target)
        expected_bodies[t['assembly_unit']].append(body)
        expected_defs[t['assembly_unit']].add(f'boom_batch_vtable{id_}')
    for s in sites:
        original = requests.sites[s['label']]
        check({k: s[k] for k in original['site']} == original['site'] and s['caller_methods'] == sorted(original['methods']),
              'Generated virtual site differs from source binding')
        cid, cp = s['caller_class'], str(s['constant']); spec = s['dispatch']
        constant = requests.constants[cid][cp]
        check(constant is not None and set(constant) == {'Method'}, 'Virtual source constant is not a method')
        value = constant['Method']; array = value['owner'].startswith('[')
        symbolic = model.root if array else model.lookup(classes[cid]['origin']['loader'], value['owner'])
        check(symbolic is not None, 'Virtual source owner is missing')
        resolved = model.resolve(symbolic, value['name'], value['descriptor'], value['interface'])
        protected = bool(model.access(resolved) & 4 and cid != model.owner(resolved)
                         and not model.same_package(cid, model.owner(resolved)))
        if array:
            text = value['owner']; element = text.lstrip('[')
            component = model.lookup(classes[cid]['origin']['loader'], element[1:-1]) if element.startswith('L') else None
            loader = classes[component]['origin']['loader'] if component is not None else 'bootstrap'
            constraint = array_index[loader, text]
        else: constraint = cid if protected else symbolic
        check(spec == dict(symbolic_owner=symbolic, receiver_constraint=constraint, resolved_owner=model.owner(resolved),
                           resolved_index=model.indices[resolved], interface=value['interface'])
              and s['resolved_method'] == resolved and s['descriptor'] == value['descriptor']
              and s['opcode'] in (182, 185), 'Virtual access/receiver contract differs from original source')
        table = table_ids[resolved, spec['interface']]
        check(s['table'] == table and s['diagnostic'] is None and isinstance(s['assembly_unit'], int), 'Virtual site not generated')
        label = s['label']
        check(label == f"boom_batch_call_{cid}_{cp}_{s['opcode']}", 'Virtual site symbol differs')
        body = f".const\nALIGN 8\nboom_batch_vconstraints_{label} QWORD OFFSET boom_t{symbolic},OFFSET boom_t{constraint}\n.code\n{label} PROC\n lea r8,boom_batch_vtable{table}\n lea r9,boom_batch_vconstraints_{label}\n jmp boom_batch_virtual_invoke\n{label} ENDP\n"
        expected_bodies[s['assembly_unit']].append(body); expected_defs[s['assembly_unit']].add(label)
    check([t['method'] for t in targets] == sorted(used_targets), 'Dispatch target coverage differs')
    for t in targets:
        id_ = t['method']; owner = model.owner(id_); c = classes[owner]
        check(t == dict(method=id_, class_id=owner, defining_loader=c['origin']['loader'], class_sha256=c['origin']['sha256'],
                        owner=c['name'], name=inventory[id_][1], descriptor=inventory[id_][2], access=model.access(id_),
                        java_assembly_emitted=id_ in requests.emitted, native_binding_provided=id_ in provided_natives), 'Dispatch target provenance differs')
    check(len(gaps) == len(requests.gaps), 'Compatibility group coverage differs')
    for gap, (key, expected) in zip(gaps, sorted(requests.gaps.items())):
        kind, protocol = key; native = int(protocol.removeprefix('native:')) if kind == 'native_declaration' else None
        if native is not None:
            c = classes[model.owner(native)]
            protocol = f"{c['origin']['loader']}:{c['name']}.{inventory[native][1]}{inventory[native][2]}"
        check((gap['kind'], gap['protocol'], gap['native_method'], gap['symbols'], gap['affected_methods']) ==
              (kind, protocol, native, sorted(expected['symbols']), sorted(expected['methods'])), 'Compatibility group identity/count differs')
        check(gap['examples'] == expected['examples'], 'Compatibility examples differ from original bindings')
        for binding in gap['examples'].values():
            value = requests.constants[binding['caller_class']][str(binding['constant'])]
            if kind in ('invokedynamic', 'dynamic_constant'):
                site = value['InvokeDynamic' if kind == 'invokedynamic' else 'Dynamic']; bootstrap = site['bootstrap']
                check(binding['protocol'] == f"{bootstrap['owner']}.{bootstrap['name']}{bootstrap['descriptor']}", 'Bootstrap protocol differs from source')
    defined, undefined = set(), set()
    check(set(expected_bodies) == set(range(len(summary['units']))), 'Dispatch assembly units have missing/extra bodies')
    for unit in summary['units']:
        id_ = unit['id']; text = artifact(root, unit['assembly'], 'dispatch').read_text(encoding='utf-8')
        check(text.endswith('\nEND\n') and text.partition('.code\n')[2][:-5] == ''.join(b+'\n' for b in expected_bodies[id_]),
              'Dispatch MASM differs from independently selected source bodies')
        check(unit['object'] and not unit['assembler_diagnostic'], 'Dispatch assembly failed')
        defs, undefs = coff_symbols(artifact(root, unit['object'], 'dispatch'))
        check(defs == expected_defs[id_], 'Dispatch COFF definitions differ')
        check(not defined & defs, 'Duplicate dispatch COFF definition')
        defined.update(defs); undefined.update(undefs)
    java_emitted = sum(t['java_assembly_emitted'] for t in targets)
    native = sum(bool(t['access'] & 0x100) for t in targets)
    counts = dict(virtual_sites=len(sites), generated_sites=len(sites), shared_tables=len(tables), generated_tables=len(tables),
                  receiver_rows=sum(len(t['rows']) for t in tables), java_targets_emitted=java_emitted,
                  java_targets_missing=len(targets)-java_emitted-native, native_targets_unbound=sum(bool(t['access']&0x100) and not t['native_binding_provided'] for t in targets),
                  pending_contract_groups=len(gaps), pending_contract_symbols=len(set().union(*(g['symbols'] for g in requests.gaps.values()))) if gaps else 0)
    check(all(summary[k] == v for k, v in counts.items()), 'Dispatch summary coverage differs')
    return dict(verified=True, **counts, scope='source_virtual_selection_MASM_and_COFF_only', execution_verified=False), defined, undefined
