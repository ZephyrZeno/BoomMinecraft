"""Source-derived MASM binding data and a native process owner, never guest code."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


S = module('native_vm_entry_io', 'runtime-provider-source.py')
R = module('native_vm_entry_original', 'verify-batch-frames.py')
FOREIGN = {'CreateFileW', 'WriteFile', 'CloseHandle', 'ExitProcess'}
EXPORTS = {'boom_vm_thread_root_cells', 'boom_vm_thread_root_count', 'boom_vm_thread_bootstrap_pool',
           'boom_vm_system_phase1_called', 'boom_vm_bootstrap_main', 'boom_process_entry',
           'boom_vm_entry_context', 'boom_vm_entry_report', 'boom_vm_child_constructor_completed',
           'boom_vm_child_start_completed', 'boom_vm_child_reaped', 'boom_vm_signal_opened', 'boom_vm_signal_closed'}
CTOR_SPECS = (
    ('java/lang/ThreadGroup', '()V'),
    ('java/lang/ThreadGroup', '(Ljava/lang/ThreadGroup;Ljava/lang/String;IZ)V'),
    ('java/security/AccessControlContext', '([Ljava/security/ProtectionDomain;Z)V'),
    ('java/lang/Thread', '(Ljava/lang/ThreadGroup;Ljava/lang/String;ILjava/lang/Runnable;JLjava/security/AccessControlContext;)V'))


def accepted(directory, proof_sha):
    directory = Path(directory).resolve()
    S.check(directory.is_relative_to(S.ART/'diagnostic-startup'), 'Use an isolated original-source diagnostic')
    proof_path = directory/'selection-verification.json'
    S.check(S.digest(proof_path)['sha256'] == proof_sha, 'Explicitly accepted source verification differs')
    proof, closure = S.read(proof_path), S.read(directory/'closure.json')
    S.check(proof['verified'] and proof['diagnostic_only'] and not proof['source_closure_complete'] and
            closure['diagnostic_only'] and not closure['source_closure_complete'], 'Native entry needs an explicit development source prefix')
    asm = (directory/'initialization-closure.asm').read_text(encoding='utf-8')
    S.check(hashlib.sha256(asm.encode()).hexdigest() == proof['closure_assembly_sha256'], 'Accepted original Java assembly changed')
    old = S.read(directory/'vm-thread-bootstrap.json')
    if proof.get('closure_manifest_sha256'):
        S.check(S.digest(directory/'closure.json')['sha256'] == proof['closure_manifest_sha256'] and
                S.digest(directory/'diagnostic.json')['sha256'] == proof['diagnostic_manifest_sha256'],
                'Independently sealed source selection changed')
        diagnostic = S.read(directory/'diagnostic.json')
        S.check(S.digest(directory/'diagnostic-stops.asm')['sha256']==diagnostic['assembly_sha256'],
                'Accepted diagnostic assembly changed')
        runtime = diagnostic['global_provider_identity']
        S.check(old['runtime'] == runtime['runtime_dll'] and
                S.digest(old['runtime'])['sha256'] == runtime['runtime_sha256'], 'Sealed runtime input differs')
        return closure, proof, old
    # Source/assembly/runtime inputs are needed here. The historical C# host and
    # its runner are provenance only; the new process does not load or call them.
    for record in old['inputs']:
        p = Path(record['path']).resolve()
        if p.is_relative_to(S.ART) or p.suffix == '.asm':
            S.check(S.artifact(p) == record, 'Accepted VM source input changed: '+str(p))
    execution = S.read(directory/'execution.json')
    S.check(execution['original_main_Thread_and_two_ThreadGroup_and_ACC_constructors_completed'] and
            execution['original_constructor_field_assertions_passed'] and
            execution['source_configuration_sha256'] == S.digest(directory/'vm-thread-bootstrap.json')['sha256'] and
            execution['source_verification_sha256'] == proof_sha and
            execution['image_sha256'] == S.digest(directory/'diagnostic-image.dll')['sha256'],
            'Baseline did not actually complete the original primordial constructors')
    return closure, proof, old


def binding_model(closure, include_system, construct_child=False, start_child=False, child_task_main_thread=False, signal_control=False, system_phase2=False):
    S.check(not system_phase2 or (include_system and signal_control), 'System phase 2 requires phase 1 and the native signal lifecycle')
    S.check(not start_child or construct_child, 'Native Thread start requires original child construction')
    S.check(not child_task_main_thread or (construct_child and start_child),
            'Runnable task verification requires a constructed and started original child')
    batch, plan = Path(closure['batch']), Path(closure['plan'])
    summary, plan_summary = S.read(batch/'summary.json'), S.read(plan/'summary.json')
    S.check(S.digest(batch/'summary.json')['sha256'] == closure['source_batch_summary_sha256'], 'Base batch changed')
    classes = [json.loads(line) for line in S.checked(plan_summary['artifacts']['classes']).open(encoding='utf-8')]
    names = {c['name']: c for c in classes if c['origin']['loader'] == 'bootstrap'}
    needed = {'java/lang/Thread', 'java/lang/ThreadGroup', 'java/security/AccessControlContext',
              'java/lang/Thread$FieldHolder', 'jdk/internal/misc/VM', 'java/lang/String',
              'java/lang/System', 'java/lang/Class', 'java/lang/reflect/Method'}
    if signal_control:
        needed.add('jdk/internal/misc/Signal')
    owners = {n: names[n] for n in needed}
    for c in owners.values():
        S.check(c['origin']['source_id'] == 'jdk:java.base' and not c['origin'].get('generated'), 'VM binding requires original bootstrap classes')
    layouts = {}
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            if row['name'] in needed and row['class_id'] == owners[row['name']]['id']:
                S.check(row['diagnostic'] is None and row['candidate'] is not None and
                        row['source_sha256'] == owners[row['name']]['origin']['sha256'], 'VM field layout identity differs')
                layouts[row['name']] = row['candidate']
    def offset(owner, name, descriptor, width):
        matches = [f for f in layouts[owner]['fields'] if f['member']['owner'] == owners[owner]['id'] and
                   (f['member']['name'], f['member']['descriptor']) == (name, descriptor)]
        S.check(len(matches) == 1 and matches[0]['storage_bytes'] == width, 'VM field width/source differs')
        f = matches[0]
        S.check(owners[owner]['fields'][f['member']['index']] ==
                {k: f['member'][k] for k in ('name', 'descriptor', 'access')}, 'Original VM field declaration differs')
        return f['offset']
    def method(owner, name, descriptor):
        c = owners[owner]
        original_name, raw = R.original_methods(S.original_class(summary, c))
        matches = [(i, m) for i, m in zip(c['method_ids'], raw) if (m['name'], m['descriptor']) == (name, descriptor)]
        S.check(original_name == owner and len(matches) == 1 and matches[0][1]['code'] is not None, 'VM source method missing')
        i, m = matches[0]
        selected = closure['selected_methods'].get(str(i))
        code_sha = hashlib.sha256(m['code'][0]).hexdigest()
        S.check(selected is not None and selected['class_id'] == c['id'] and
                selected['code_sha256'] == code_sha and selected['source_sha256'] == c['origin']['sha256'],
                'VM upcall is not the selected original Java method')
        return dict(owner=owner, name=name, descriptor=descriptor, method=i, symbol=f'boom_m{i}',
                    code_sha256=code_sha, class_sha256=c['origin']['sha256'])
    ctors = [method(n, '<init>', d) for n, d in CTOR_SPECS]
    child_descriptor = ('(Ljava/lang/ThreadGroup;Ljava/lang/Runnable;Ljava/lang/String;)V'
                        if child_task_main_thread else '(Ljava/lang/ThreadGroup;Ljava/lang/String;)V')
    child = method('java/lang/Thread', '<init>', child_descriptor) if construct_child else None
    child_start = method('java/lang/Thread', 'start', '()V') if start_child else None
    lifecycle = None
    if start_child:
        candidates = [(i, ref, S.read(S.checked(ref['manifest']))) for i, ref in enumerate(closure['runtime_provider_packs'])]
        found = [(i, ref, m) for i, ref, m in candidates if m['family'] == 'normal-thread-start-v1']
        S.check(len(found) == 1 and found[0][0] in closure['selected_runtime_provider_packs'],
                'Native Thread start needs the selected original-source lifecycle provider')
        _, ref, provider = found[0]
        meta = S.read(S.checked(provider['normal_thread_start_metadata']))
        S.check((meta['thread_class'],meta['pool_bytes'],meta['pool_abi'],meta['start_bytes'],meta['start_abi']) ==
                (owners['java/lang/Thread']['id'],256,1,88,2), 'Native Thread lifecycle binding ABI differs')
        lifecycle = dict(manifest=ref['manifest'], metadata=provider['normal_thread_start_metadata'])
    system = method('java/lang/System', 'initPhase1', '()V') if include_system else None
    level = [i for i, f in enumerate(owners['jdk/internal/misc/VM']['fields']) if
             (f['name'], f['descriptor']) == ('initLevel', 'I') and f['access'] & 8]
    S.check(len(level) == 1, 'Original VM.initLevel field missing')
    literal = None
    with zipfile.ZipFile(S.checked(summary['string_literals']['index'])) as z:
        for line in z.open('canonical.jsonl'):
            row = json.loads(line)
            if row['utf16'] == [109, 97, 105, 110]:
                S.check(literal is None, 'Ambiguous original main literal')
                literal = row['id']
    S.check(literal is not None, 'Original main literal missing')
    model = dict(schema=1, pool_bytes=192, pool_abi=1, registry_capacity=64,
        classes={n: c['id'] for n, c in owners.items()}, constructors=ctors, system_entry=system, child_constructor=child,
        child_start=child_start, lifecycle_reference=lifecycle,
        main_literal_id=literal, vm_level_symbol=f"boom_s{owners['jdk/internal/misc/VM']['id']}_{level[0]}",
        offsets=dict(eetop=offset('java/lang/Thread', 'eetop', 'J', 8),
            holder=offset('java/lang/Thread', 'holder', 'Ljava/lang/Thread$FieldHolder;', 8),
            status=offset('java/lang/Thread$FieldHolder', 'threadStatus', 'I', 4),
            tid=offset('java/lang/Thread', 'tid', 'J', 8)),
        prerequisite_classes=[owners[n]['id'] for n in ('java/lang/String', 'java/lang/System', 'java/lang/Class', 'java/lang/reflect/Method')])
    if child_task_main_thread:
        model['child_task'] = dict(kind='original_main_Thread_as_Runnable',
            holder_task_offset=offset('java/lang/Thread$FieldHolder', 'task', 'Ljava/lang/Runnable;', 8))
    if system_phase2:
        phases=module('native_phase2_original_source','vm-system-phase2.py')
        model['system_phase2']=phases.bind(closure,summary,owners['java/lang/System'],S,R)
        model['phase2_context_rows']=closure.get('diagnostic_context_rows',False)
    if signal_control:
        found = [(i, ref, S.read(S.checked(ref['manifest']))) for i, ref in enumerate(closure['runtime_provider_packs'])
                 if S.read(S.checked(ref['manifest']))['family'] == 'normal-signal-control-v1']
        S.check(len(found) == 1 and found[0][0] in closure['selected_runtime_provider_packs'],
                'Native signal control needs the selected original-source provider')
        _, ref, provider = found[0]
        meta = S.read(S.checked(provider['normal_signal_control_metadata']))
        S.check((meta['thread_class'],meta['pool_bytes'],meta['pool_abi'],meta['transport_config_abi']) ==
                (owners['java/lang/Thread']['id'],256,1,2), 'Native signal lifecycle ABI differs')
        for call in meta['upcalls']:
            S.check(method(call['owner'],call['name'],call['descriptor'])['method'] == call['method'],
                    'Native signal callback does not match selected original Java')
        model['signal_reference'] = dict(manifest=ref['manifest'], metadata=provider['normal_signal_control_metadata'])
    if signal_control or start_child:
        selected = [(ref, S.read(S.checked(ref['manifest']))) for i,ref in enumerate(closure['runtime_provider_packs'])
                    if i in closure['selected_runtime_provider_packs']]
        pending = [(ref,p) for ref,p in selected if p['family']=='normal-reference-processing-v1']
        if pending:
            S.check(len(pending)==1 and any(p['family']=='normal-thread-start-v1' and
                    'boom_provider_threads_control_binding' in p['exports'] for _,p in selected),
                    'Reference processing requires the native worker shutdown boundary')
            ref,p = pending[0]
            model['reference_processing'] = dict(manifest=ref['manifest'],metadata=p['reference_processing_metadata'])
        waiting=[(ref,p) for ref,p in selected if p['family']=='normal-object-wait-v1']
        if waiting:
            S.check(len(waiting)==1 and len(pending)==1 and 'boom_provider_reference_issue_stop' in pending[0][1]['exports'],
                    'Object.wait0 needs the shared platform-worker cancellation boundary')
            ref,p=waiting[0]
            model['object_wait']=dict(manifest=ref['manifest'],metadata=p['object_wait_metadata'])
        windows = [(ref,p) for ref,p in selected if p['family']=='normal-winnt-filesystem-v1']
        if windows:
            S.check(len(windows)==1,'Ambiguous Windows filesystem provider')
            ref,p=windows[0]
            model['winnt_filesystem']=dict(manifest=ref['manifest'],metadata=p['winnt_filesystem_metadata'])
    return model


def report_layout(model):
    if model.get('object_wait'):return 448,11
    if model.get('winnt_filesystem'):return 400,10
    if model.get('reference_processing'):return 384,9
    if model.get('phase2_context_rows'):return 320,8
    if model.get('system_phase2'):return 312,7
    return (272,6) if model.get('signal_reference') or model['child_start'] else (112,2)


def assembly(model):
    c, o = model['classes'], model['offsets']
    pointers = ['boom_heap_ptr', 'boom_provider_thread_registry', 'boom_vm_thread_root_cells', 'boom_provider_thread_pool',
        f"boom_layout{c['java/lang/Thread']}", f"boom_layout{c['java/lang/ThreadGroup']}", f"boom_layout{c['java/security/AccessControlContext']}",
        f"boom_class{c['java/lang/Thread']}", f"boom_class{c['java/lang/ThreadGroup']}", f"boom_class{c['java/security/AccessControlContext']}",
        f"boom_class{c['jdk/internal/misc/VM']}", model['vm_level_symbol'], 'boom_java_string_literal', 'boom_java_string_literal_pool']
    proc = {'boom_class_ensure32', 'boom_vm_thread_bootstrap', 'boom_java_string_literal'} | {r['symbol'] for r in model['constructors']}
    if model['system_entry']:
        proc.add(model['system_entry']['symbol'])
    if model.get('system_phase2'):
        proc.add(model['system_phase2']['symbol'])
    if model['child_constructor']:
        proc.update({model['child_constructor']['symbol'], 'boom_object_new', 'boom_threads_current'})
    if model['child_start']:
        proc.update({model['child_start']['symbol'], 'boom_provider_threads_reap', 'Sleep'})
    if model['child_start'] or model.get('signal_reference'):
        proc.update({'Sleep','GetTickCount64'})
    if model.get('signal_reference'):
        proc.add('boom_provider_signal_open')
    data = set(pointers)-{'boom_vm_thread_root_cells', 'boom_java_string_literal'}
    if model.get('reference_processing'):
        data.update(('boom_provider_reference_pool','boom_provider_threads_control_binding'))
        proc.update('boom_provider_reference_'+n for n in ('open','stop','close','boundary'))
    if model.get('object_wait'):
        data.add('boom_provider_object_wait_pool')
        proc.update('boom_provider_object_wait_'+s for s in ('open','stop','close'))
    if model.get('winnt_filesystem'):data.add('boom_provider_winnt_file_pool')
    if model.get('signal_reference'):
        data.add('boom_provider_signal_pool')
    if model.get('phase2_context_rows'):
        data.add('boom_diagnostic_context_map')
        proc.add('boom_diagnostic_context_map_row')
    data.update(f'boom_class{i}' for i in model['prerequisite_classes'])
    template = (ROOT/'native/entry/vm_process.asm.inc').read_text(encoding='utf-8')
    externals = dict(re.findall(r'(?m)^EXTERN (\w+):(\w+)$', template))
    if not model['child_start'] and not model.get('signal_reference'):
        for symbol in ('boom_provider_threads_pool','boom_provider_threads_close','boom_provider_thread_priority_pool'):
            externals.pop(symbol,None)
    if not model.get('signal_reference'):
        for symbol in ('boom_provider_signal_pool','boom_provider_signal_close'):
            externals.pop(symbol,None)
    template = re.sub(r'(?m)^EXTERN \w+:\w+\n', '', template)
    externals.update({s: 'BYTE' for s in data})
    externals.update({s: 'PROC' for s in proc})
    report_bytes,report_abi=report_layout(model)
    phase2_definitions=''
    if model.get('system_phase2'):
        phase2_definitions=(f"VM_ENTRY_SYSTEM_PHASE2 EQU 1\nVM_LEVEL_CELL TEXTEQU <{model['vm_level_symbol']}>\n"
                            f"ORIGINAL_SYSTEM_PHASE2 TEXTEQU <{model['system_phase2']['symbol']}>\n")
        if model.get('phase2_context_rows'):phase2_definitions+='VM_ENTRY_MAIN_SOURCE_ROW EQU 1\n'
    if model.get('reference_processing'):phase2_definitions+='VM_ENTRY_REFERENCE_PROCESSING EQU 1\n'
    if model.get('object_wait'):phase2_definitions+='VM_ENTRY_OBJECT_WAIT EQU 1\n'
    if model.get('winnt_filesystem'):phase2_definitions+='VM_ENTRY_WINNT_FILESYSTEM EQU 1\n'
    out = (f"option casemap:none\nVM_ENTRY_CHILD_REQUESTED EQU {int(model['child_constructor'] is not None)}\n"
        f"VM_ENTRY_START_REQUESTED EQU {int(model['child_start'] is not None)}\n"
        f"VM_ENTRY_SIGNAL_REQUESTED EQU {int(bool(model.get('signal_reference')))}\n"
        f"VM_ENTRY_REPORT_BYTES EQU {report_bytes}\nVM_ENTRY_REPORT_ABI EQU {report_abi}\n"
        +phase2_definitions)+''.join(f'EXTERN {s}:{t}\n' for s, t in sorted(externals.items()))
    root_count = 6 if model['child_constructor'] else 5
    out += f'.data?\nALIGN 8\nPUBLIC boom_vm_thread_root_cells\nboom_vm_thread_root_cells QWORD {root_count} DUP(?)\n'
    out += f'.const\nPUBLIC boom_vm_thread_root_count\nboom_vm_thread_root_count QWORD {root_count}\n.data\nALIGN 8\nPUBLIC boom_vm_thread_bootstrap_pool\nboom_vm_thread_bootstrap_pool DWORD 056544250h,1,0,64\n'
    out += ''.join(f' QWORD OFFSET {s}\n' for s in pointers)
    out += f" DWORD {model['main_literal_id']},{o['eetop']},{o['holder']},{o['status']}\n"
    out += ''.join(f" QWORD OFFSET {r['symbol']}\n" for r in model['constructors'])
    out += f" DWORD {o['tid']},0\n QWORD 0\nPUBLIC boom_vm_system_phase1_called\nboom_vm_system_phase1_called DWORD 0\n"
    out += 'PUBLIC boom_vm_child_constructor_completed\nboom_vm_child_constructor_completed DWORD 0\n'
    out += 'PUBLIC boom_vm_child_start_completed\nboom_vm_child_start_completed DWORD 0\nPUBLIC boom_vm_child_reaped\nboom_vm_child_reaped DWORD 0\n'
    out += 'PUBLIC boom_vm_signal_opened\nboom_vm_signal_opened DWORD 0\nPUBLIC boom_vm_signal_closed\nboom_vm_signal_closed DWORD 0\n'
    out += '.code\nPUBLIC boom_vm_bootstrap_main\nboom_vm_bootstrap_main PROC FRAME\n push rbx\n .pushreg rbx\n sub rsp,64\n .allocstack 64\n .endprolog\n mov rbx,rcx\n test rbx,rbx\n jz vbm_zero\n cmp DWORD PTR [rbx],0\n jne vbm_zero\n'
    for i in model['prerequisite_classes']:
        out += f' lea rcx,boom_class{i}\n mov rdx,rbx\n call boom_class_ensure32\n cmp DWORD PTR [rbx],0\n jne vbm_zero\n'
    out += ' mov rcx,rbx\n lea rdx,boom_vm_thread_bootstrap_pool\n call boom_vm_thread_bootstrap\n cmp DWORD PTR [rbx],0\n jne vbm_zero\n'
    if model.get('object_wait'):
        out += (' lea rcx,boom_provider_object_wait_pool\n call boom_provider_object_wait_open\n test eax,eax\n jz vbm_wait_ready\n'
                ' mov DWORD PTR [boom_vm_entry_report+412],eax\n mov DWORD PTR [rbx],7\n jmp vbm_zero\n'
                'vbm_wait_ready:\n mov DWORD PTR [boom_vm_entry_report+400],1\n')
    if model['child_constructor']:
        out += (f" mov rcx,QWORD PTR [boom_heap_ptr]\n lea rdx,boom_layout{c['java/lang/Thread']}\n mov r8,rbx\n call boom_object_new\n"
            ' test rax,rax\n jz vbm_zero\n mov QWORD PTR [boom_vm_thread_root_cells+40],rax\n mov QWORD PTR [rsp+32],rax\n'
            ' mov rax,QWORD PTR [boom_vm_thread_root_cells+16]\n mov QWORD PTR [rsp+40],rax\n'
            + (' mov rax,QWORD PTR [boom_vm_thread_root_cells]\n mov QWORD PTR [rsp+48],rax\n'
               ' mov rax,QWORD PTR [boom_vm_thread_root_cells+32]\n mov QWORD PTR [rsp+56],rax\n'
               if model.get('child_task') else
               ' mov rax,QWORD PTR [boom_vm_thread_root_cells+32]\n mov QWORD PTR [rsp+48],rax\n')
            + ' mov rcx,rbx\n lea rdx,[rsp+32]\n'
            f" call {model['child_constructor']['symbol']}\n cmp DWORD PTR [rbx],0\n jne vbm_zero\n"
            ' mov r10,QWORD PTR [boom_vm_thread_root_cells+40]\n'
            f" cmp QWORD PTR [r10+{o['tid']}],2\n jne vbm_child_bad\n cmp QWORD PTR [r10+{o['eetop']}],0\n jne vbm_child_bad\n"
            f" mov r10,QWORD PTR [r10+{o['holder']}]\n test r10,r10\n jz vbm_child_bad\n"
            f" cmp DWORD PTR [r10+{o['status']}],0\n jne vbm_child_bad\n"
            + (f" mov rax,QWORD PTR [boom_vm_thread_root_cells]\n cmp QWORD PTR [r10+{model['child_task']['holder_task_offset']}],rax\n jne vbm_child_bad\n"
               if model.get('child_task') else '')
            +
            ' mov rcx,QWORD PTR [boom_provider_thread_registry]\n call boom_threads_current\n cmp rax,QWORD PTR [boom_vm_thread_root_cells]\n jne vbm_child_bad\n'
            ' mov DWORD PTR [boom_vm_child_constructor_completed],1\n jmp vbm_child_done\nvbm_child_bad:\n mov DWORD PTR [rbx],7\n jmp vbm_zero\nvbm_child_done:\n')
    if model['child_start']:
        out += (' mov rax,QWORD PTR [boom_vm_thread_root_cells+40]\n mov QWORD PTR [rsp+32],rax\n'
            ' mov rcx,rbx\n lea rdx,[rsp+32]\n'
            f" call {model['child_start']['symbol']}\n cmp DWORD PTR [rbx],0\n jne vbm_zero\n"
            ' mov DWORD PTR [boom_vm_child_start_completed],1\n mov DWORD PTR [rsp+56],20000\n'
            'vbm_child_reap_loop:\n lea rcx,boom_provider_threads_pool\n mov rdx,QWORD PTR [boom_vm_thread_root_cells+40]\n'
            ' call boom_provider_threads_reap\n test eax,eax\n jz vbm_child_reaped\n cmp eax,170\n jne vbm_child_bad\n'
            ' dec DWORD PTR [rsp+56]\n jz vbm_child_bad\n mov ecx,1\n call Sleep\n jmp vbm_child_reap_loop\n'
            'vbm_child_reaped:\n mov DWORD PTR [boom_vm_child_reaped],1\n'
            ' cmp DWORD PTR [boom_provider_threads_pool+120],2\n jne vbm_child_no_worker_failure\n'
            ' mov r10,QWORD PTR [boom_provider_threads_pool+224]\n mov rax,QWORD PTR [r10]\n mov QWORD PTR [rbx],rax\n'
            ' mov rax,QWORD PTR [r10+8]\n mov QWORD PTR [rbx+8],rax\n mov rax,QWORD PTR [r10+16]\n mov QWORD PTR [rbx+16],rax\n'
            ' mov rax,QWORD PTR [r10+24]\n mov QWORD PTR [rbx+24],rax\n jmp vbm_zero\n'
            'vbm_child_no_worker_failure:\n cmp DWORD PTR [boom_provider_threads_pool+120],0\n jne vbm_child_bad\n'
            ' cmp QWORD PTR [boom_provider_threads_pool+168],1\n jne vbm_child_bad\n'
            ' cmp QWORD PTR [boom_provider_threads_pool+176],1\n jne vbm_child_bad\n'
            ' cmp QWORD PTR [boom_provider_threads_pool+184],1\n jne vbm_child_bad\n'
            ' cmp QWORD PTR [boom_provider_threads_pool+192],0\n jne vbm_child_bad\n'
            ' cmp QWORD PTR [boom_provider_threads_pool+200],1\n jne vbm_child_bad\n'
            ' cmp QWORD PTR [boom_provider_threads_pool+208],1\n jne vbm_child_bad\n'
            ' cmp QWORD PTR [boom_provider_threads_pool+216],1\n jne vbm_child_bad\n'
            ' mov r10,QWORD PTR [boom_vm_thread_root_cells+40]\n'
            f" cmp QWORD PTR [r10+{o['eetop']}],0\n jne vbm_child_bad\n mov r10,QWORD PTR [r10+{o['holder']}]\n"
            f" cmp DWORD PTR [r10+{o['status']}],2\n jne vbm_child_bad\n")
    if model.get('signal_reference'):
        out += (' mov rcx,rbx\n mov rdx,QWORD PTR [boom_vm_thread_root_cells+16]\n lea r8,boom_provider_signal_pool\n'
            ' call boom_provider_signal_open\n cmp DWORD PTR [rbx],0\n jne vbm_zero\n test rax,rax\n jz vbm_signal_bad\n'
            ' mov DWORD PTR [boom_vm_signal_opened],1\n')
    if model['system_entry']:
        out += ' mov DWORD PTR [boom_vm_system_phase1_called],1\n mov rcx,rbx\n xor edx,edx\n'
        out += f" call {model['system_entry']['symbol']}\n cmp DWORD PTR [rbx],0\n jne vbm_zero\n"
    if model.get('signal_reference'):
        out += ' jmp vbm_signal_good\nvbm_signal_bad:\n mov DWORD PTR [rbx],7\n jmp vbm_zero\nvbm_signal_good:\n'
    out += ' mov rax,QWORD PTR [boom_vm_thread_root_cells]\n jmp vbm_done\nvbm_zero:\n xor eax,eax\nvbm_done:\n add rsp,64\n pop rbx\n ret\nboom_vm_bootstrap_main ENDP\n'
    if model.get('system_phase2'):
        out += (ROOT/'native/entry/system_phase2.asm.inc').read_text(encoding='utf-8')+'\n'
    out += template+'\nEND\n'
    return out, set(externals)


def source_objects(closure):
    records = {}
    def collect(value):
        if isinstance(value, dict):
            if isinstance(value.get('path'), str) and isinstance(value.get('digest'), dict) and 'sha256' in value['digest']:
                records[str(Path(value['path']).resolve()).casefold()] = value
            for v in value.values():
                collect(v)
        elif isinstance(value, list):
            for v in value:
                collect(v)
    collect(S.read(Path(closure['batch'])/'summary.json'))
    collect(closure)
    for p in closure.get('runtime_provider_packs', []):
        collect(S.read(S.checked(p['manifest'])))
    result = []
    for name in closure['objects']:
        record = records.get(str(Path(name).resolve()).casefold())
        S.check(record is not None, 'Selected object has no source-bound digest: '+name)
        result.append(S.artifact(S.checked(record)))
    return result


def pe(path):
    data = Path(path).read_bytes()
    S.check(data[:2] == b'MZ', 'Expected native PE image')
    h = struct.unpack_from('<I', data, 60)[0]
    S.check(data[h:h+4] == b'PE\0\0', 'Invalid PE signature')
    machine, count = struct.unpack_from('<HH', data, h+4)
    size, flags = struct.unpack_from('<HH', data, h+20)
    optional = h+24
    S.check(machine == 0x8664 and 1 <= count <= 96 and struct.unpack_from('<H', data, optional)[0] == 0x20b, 'Expected native AMD64 PE32+')
    sections = [struct.unpack_from('<IIII', data, optional+size+i*40+8) for i in range(count)]
    def pos(rva):
        for virtual_size, virtual, raw_size, raw in sections:
            if virtual <= rva < virtual+raw_size:
                return raw+rva-virtual
        raise ValueError('PE import outside raw sections')
    def name(rva):
        at = pos(rva);end = data.find(b'\0', at, at+4096)
        S.check(end >= at, 'Unterminated PE import')
        return data[at:end].decode('ascii')
    imports = {}
    rva = struct.unpack_from('<I', data, optional+120)[0]
    if rva:
        at = pos(rva)
        for index in range(256):
            original, _, _, dll, first = struct.unpack_from('<IIIII', data, at+index*20)
            if not (original or dll or first):
                break
            S.check(dll != 0 and (original or first) != 0, 'Malformed PE import descriptor')
            dll_name = name(dll).lower(); symbols = []
            thunk = pos(original or first)
            for i in range(65536):
                value = struct.unpack_from('<Q', data, thunk+i*8)[0]
                if not value:
                    break
                symbols.append('#'+str(value & 0xffff) if value >> 63 else name(value+2))
            imports[dll_name] = symbols
        else:
            raise ValueError('PE import descriptor limit exceeded')
    return dict(machine=machine, dll=bool(flags & 0x2000), entry_rva=struct.unpack_from('<I', data, optional+16)[0],
                subsystem=struct.unpack_from('<H', data, optional+68)[0], imports=imports)
