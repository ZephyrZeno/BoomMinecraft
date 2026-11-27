"""Source-derived pure MASM process owner for a readonly JIMAGE mapping.

This is a development source generator. It does not register a provider, build
Java, execute a VM, or change a source-acceptance envelope.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PureWindowsPath
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = 'native/probe/main_jimage_owner.asm.tpl'
EXPORTS = {'boom_main_jimage_prepare', 'boom_main_jimage_unload_modules',
    'boom_main_jimage_resources_close', 'boom_main_jimage_write_report',
    'boom_main_jimage_modules_key', 'boom_main_jimage_owner', 'boom_main_jimage_report'}
REPORT_FIELDS = dict(magic=0, abi=4, bytes=8, lifecycle_flags=12,
    prepare_status=16, unload_status=20, bridge_close_status=24,
    bootstrap_release_status=28, owner_close_status=32, original_Context_preserved=36,
    unload_calls=40, pins_before=48, pins_after=56, owner_leases_before=64,
    owner_leases_after=72, bridge_nodes_before=80, bridge_nodes_after=88,
    bridge_leases_before=96, bridge_leases_after=104, files=112, maps=120,
    original_Context_snapshot=128, independent_cleanup_Context=160,
    bootstrap_view=192, bootstrap_length=200)


def check(value, message):
    if not value:
        raise ValueError(message)


def module(name, root=None):
    root = ROOT if root is None else Path(root)
    spec = importlib.util.spec_from_file_location('main_jimage_source_' + name, root / 'scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def units(text):
    raw = text.encode('utf-16-le', 'surrogatepass')
    return [int.from_bytes(raw[at:at+2], 'little') for at in range(0, len(raw), 2)]


def index(summary, classes, S, root=None):
    """Derive every image path, source method and literal ID from original inputs."""
    root = S.ROOT if root is None else Path(root)
    J = module('jimage-native-map-source', root)
    L = module('native-library-jimage-source', root)
    image_source = J.index(summary, classes, S)
    library_source = L.index(summary, classes, S)
    [unload] = [row for row in library_source['methods'] if row['name'] == 'unload']
    check(unload['owner'] == 'jdk/internal/loader/NativeLibraries' and
        unload['descriptor'] == '(Ljava/lang/String;ZJ)V' and unload['access'] == 0x10a,
        'Original source unload declaration differs')
    catalog_file = S.checked(summary['frames']['original_system_catalog'])
    catalog = S.read(catalog_file)
    image = catalog['image']
    check(S.digest(image['path']) == {key:image['digest'][key] for key in ('size', 'sha256')} and
        28 <= image['digest']['size'] <= 0x7fffffff, 'Original locked runtime image differs or exceeds original buffer capacity')
    home = summary['properties']['vm_profile']['java_home']
    windows_home = PureWindowsPath(home)
    check(windows_home.is_absolute() and str(windows_home) == home and '\0' not in home and
        all(part not in ('.', '..') for part in windows_home.parts), 'Exact declared Windows Java-home form required')
    key = str(windows_home / 'lib' / 'modules')
    check(0 < len(units(key)) <= 32767, 'Original owner UTF16 key budget exceeded')
    property_index = S.checked(summary['properties']['index'])
    with zipfile.ZipFile(property_index) as archive:
        pairs = [json.loads(line) for line in archive.open('vm.jsonl')]
        texts = {row['id']:row['utf16'] for line in archive.open('strings.jsonl') if (row:=json.loads(line))}
    [home_row] = [row for row in pairs if row['name'] == 'java.home']
    check(texts[home_row['key_literal']] == units('java.home') and texts[home_row['value_literal']] == units(home),
        'Original generated VM property Java-home literal differs')
    strings_index = S.checked(summary['string_literals']['index'])
    wanted = {name:units(name) for name in ('jimage', 'nio', 'net')}
    literals = {}
    with zipfile.ZipFile(strings_index) as archive:
        for line in archive.open('canonical.jsonl'):
            row = json.loads(line)
            for name, values in wanted.items():
                if row['utf16'] == values:
                    check(name not in literals, 'Duplicate original canonical module literal')
                    literals[name] = row['id']
    check(set(literals) == set(wanted), 'Missing original source module literals')
    return dict(schema=1, kind='native_main_jimage_process_owner_source',
        original_system_catalog=S.artifact(catalog_file), original_modules_image=image,
        original_properties_index=S.artifact(property_index), original_String_literal_index=S.artifact(strings_index),
        java_home=home, exact_modules_key=key, exact_modules_UTF16=units(key),
        expected_modules_bytes=image['digest']['size'], module_literal_ids=literals,
        original_unload_native=unload, original_JMAP_native=image_source['methods'][0],
        original_Java_callbacks=image_source['original_java'] + image_source['owner_initializer_source'],
        image_class_roots=image_source['required_classes'],
        map_source_policy=J.POLICY, library_source_policy=L.POLICY,
        report_bytes=256, report_abi=1, report_fields=dict(REPORT_FIELDS),
        native_owner_bytes=128, native_owner_capacity=32, bootstrap_job_bytes=64,
        original_main_Context_bytes=32, cleanup_Context_bytes=32,
        exports=sorted(EXPORTS), additional_oop_root_banks=0, automatic_gc=False,
        declaration_Frame8_must_be_verified_by_caller=True, native_objects_in_original_fullV=False,
        source_only=True, assembled=False, linked=False, executed=False, game_started=False)


def render(model, template):
    check(model['schema'] == 1 and model['kind'] == 'native_main_jimage_process_owner_source' and
        model['exact_modules_UTF16'] == units(model['exact_modules_key']) and
        model['report_bytes'] == 256 and model['report_abi'] == 1 and model['exports'] == sorted(EXPORTS),
        'Native resource-owner source model differs')
    values = model['exact_modules_UTF16']
    bindings = dict(MODULE_KEY_WORDS='\n'.join(' WORD ' + ','.join(f'0{value:04X}h' for value in values[at:at+16])
        for at in range(0,len(values),16)), MODULE_UNITS=str(len(values)), MODULE_BYTES=str(model['expected_modules_bytes']),
        UNLOAD_SYMBOL='boom_m' + str(model['original_unload_native']['method']),
        JIMAGE_LITERAL=str(model['module_literal_ids']['jimage']), NIO_LITERAL=str(model['module_literal_ids']['nio']),
        NET_LITERAL=str(model['module_literal_ids']['net']))
    text = template
    check(set(re.findall(r'@([A-Z_]+)@', text)) == set(bindings), 'Unknown or missing native-owner source bindings')
    for name, value in bindings.items():
        text = text.replace('@' + name + '@', value)
    return text


def derive_process(template):
    edits = []

    def replace(name, old, new):
        nonlocal template
        check(template.count(old) == 1, 'One exact standard VM anchor required: ' + name)
        edits.append(dict(name=name, before=old, after=new))
        template = template.replace(old, new, 1)

    original = template
    imports = ('EXTERN boom_main_jimage_prepare:PROC\nEXTERN boom_main_jimage_unload_modules:PROC\n'
        'EXTERN boom_main_jimage_resources_close:PROC\nEXTERN boom_main_jimage_write_report:PROC\n')
    replace('native_imports_only', 'EXTERN boom_heap_create:PROC\n', imports + 'EXTERN boom_heap_create:PROC\n')
    begin = ' or DWORD PTR [boom_vm_entry_report+8],2\n'
    replace('prepare_before_every_Java_bootstrap_call', begin, begin +
        ' call boom_main_jimage_prepare\n test eax,eax\n jz vpe_jimage_prepared\n'
        ' mov DWORD PTR [boom_vm_entry_report+68],eax\n jmp vpe_capture\nvpe_jimage_prepared:\n')
    joined = 'vpe_all_workers_joined:\nENDIF\n'
    replace('unload_after_join_before_roots_detach_and_heap', joined, joined +
        ' lea rcx,boom_vm_entry_context\n call boom_main_jimage_unload_modules\n test eax,eax\n'
        ' jz vpe_jimage_modules_unloaded\n mov DWORD PTR [boom_vm_entry_report+68],eax\n'
        ' cmp DWORD PTR [boom_vm_entry_report+80],86\n je vpe_report\n'
        ' mov DWORD PTR [boom_vm_entry_report+80],70\n jmp vpe_report\nvpe_jimage_modules_unloaded:\n')
    frame_error = 'vpe_frame_error:\n mov DWORD PTR [boom_vm_entry_report+68],eax\n'
    replace('retain_all_VM_memory_if_trace_release_failed', frame_error, frame_error +
        ' cmp DWORD PTR [boom_vm_entry_report+80],86\n je vpe_report\n'
        ' mov DWORD PTR [boom_vm_entry_report+80],70\n jmp vpe_report\n')
    freed = ' or DWORD PTR [boom_vm_entry_report+64],1\nvpe_report:\n'
    replace('release_mapping_only_after_actual_heap_destroy_success', freed,
        ' or DWORD PTR [boom_vm_entry_report+64],1\n call boom_main_jimage_resources_close\n'
        ' test eax,eax\n jz vpe_report\n mov DWORD PTR [boom_vm_entry_report+68],eax\n'
        ' cmp DWORD PTR [boom_vm_entry_report+80],86\n je vpe_report\n'
        ' mov DWORD PTR [boom_vm_entry_report+80],70\nvpe_report:\n')
    report = 'vpe_report:\n ; CREATE_NEW prevents a repeated process run from replacing prior evidence.\n'
    replace('additional_native_sidecar_report_keep_original_Context_and_report_ABI', report,
        'vpe_report:\n call boom_main_jimage_write_report\n test eax,eax\n jz vpe_jimage_report_done\n'
        ' mov DWORD PTR [boom_vm_entry_report+68],eax\n cmp DWORD PTR [boom_vm_entry_report+80],86\n'
        ' je vpe_jimage_report_done\n mov DWORD PTR [boom_vm_entry_report+80],74\nvpe_jimage_report_done:\n'
        ' ; CREATE_NEW prevents a repeated process run from replacing prior evidence.\n')
    restored = template
    for edit in reversed(edits):
        check(restored.count(edit['after']) == 1, 'Ambiguous inverse entry delta: ' + edit['name'])
        restored = restored.replace(edit['after'], edit['before'], 1)
    check(restored == original, 'Native entry delta does not recover exact original bytes')
    return template, edits


def stage_modules(model, S):
    """Create only the missing project-owned image input; never overwrite one."""
    original = model['original_modules_image']
    source = Path(original['path']).resolve()
    check(S.digest(source) == {key:original['digest'][key] for key in ('size','sha256')}, 'Locked source modules changed')
    target = Path(model['exact_modules_key'])
    check(target.is_absolute() and target.resolve().is_relative_to(S.ART) and str(target) == model['exact_modules_key'],
        'Native image input must remain at its exact source-declared project Java-home key')
    if target.parent.exists():
        check(target.parent.is_dir() and not target.parent.is_symlink() and target.parent.resolve().is_relative_to(S.ART),
            'Existing lib path escaped isolated project artifacts')
    else:
        target.parent.mkdir(parents=True)
    before = S.artifact(target) if target.exists() else None
    original_before = S.artifact(source)
    if before is None:
        with source.open('rb') as input_stream, target.open('xb') as output_stream:
            shutil.copyfileobj(input_stream, output_stream, 1024*1024)
    after = S.artifact(target)
    check(after['digest'] == original_before['digest'] and S.artifact(source) == original_before,
        'Exact source image staging failed')
    return dict(verified=True, source_before=original_before, source_after=S.artifact(source),
        target_before=before, target_after=after, created_new=before is None,
        original_properties_or_Java_modified=False, target_key=model['exact_modules_key'],
        target_UTF16=model['exact_modules_UTF16'], game_started=False)


def prepare(state_file, output, root=None, stage=False):
    root = ROOT if root is None else Path(root).resolve()
    F = module('formal-provider-selection', root)
    S = F.S
    state, paths, _ = F.state_inputs(state_file)
    initial_tools = S.tools_identity()
    identity, summary, classes = S.base(paths['batch'], paths['plan'])
    check(identity['batch_summary']['digest']['sha256'] == state['batch_summary_sha256'] and
        identity['base_verification']['digest']['sha256'] == state['batch_verification_sha256'], 'Actual source batch/fullV changed')
    module('refresh-named-module-batch', root).verified_resolver(paths['batch'], summary, paths['plan'])
    frame_file = Path(state['frame_manifest'])
    frame = module('native-frame-overlay', root)
    check(frame.verify(frame_file,paths['batch'],paths['plan']) == S.read(frame_file.with_name('verification.json')) and
        S.digest(frame_file.with_name('verification.json'))['sha256'] == state['frame_verification_sha256'],
        'Actual source Frame8 changed')
    model = index(summary,classes,S,root)
    declarations = {row['id']:row for row in S.read(frame_file)['source']['original_native_declarations']}
    for row in (model['original_unload_native'], model['original_JMAP_native']):
        native = declarations[row['method']]
        check(native['flags'] & 32 and not native['flags'] & 128 and
            all(native[key] == row[key] for key in ('class_id','class_sha256','loader','source_id','name','descriptor','access')),
            'Original native source Frame8 declaration differs')
    output = Path(output).resolve()
    check(output.is_relative_to(S.ART) and not output.exists(), 'Fresh isolated source-owner output required')
    template_file = Path(__file__).resolve().parents[1]/TEMPLATE
    template = template_file.read_text(encoding='utf-8')
    text = render(model,template)
    original_process = root/'native/entry/vm_process.asm.inc'
    derived, edits = derive_process(original_process.read_text(encoding='utf-8'))
    output.mkdir(parents=True)
    module_stage = stage_modules(model,S) if stage else None
    (output/'owner.asm').write_text(text,encoding='utf-8',newline='\n')
    (output/'derived-vm-process.asm.inc').write_text(derived,encoding='utf-8',newline='\n')
    S.write(output/'model.json',model)
    check(S.tools_identity() == initial_tools == state['tool_sources'], 'Current shared namespace changed during source generation')
    record = dict(schema=1,scope='new_native_owner_source_and_six_reversible_process_text_edits_only',
        input_state=S.artifact(state_file), original_status=state['status'], base=identity,
        source_model=S.artifact(output/'model.json'), template=S.artifact(template_file), source=S.artifact(output/'owner.asm'),
        original_process=S.artifact(original_process), derived_process=S.artifact(output/'derived-vm-process.asm.inc'),
        native_process_text_edits=edits, native_process_text_edit_count=6,
        meaningful_hook_count=4, additional_edits=['EXTERN declarations','trace-release failure retains VM memory and jumps to report'],
        producer=S.artifact(__file__), tools=initial_tools, staged_modules=module_stage,
        Frame8_verified=True, source_only=True, assembled=False, linked=False, executed=False,
        fullVM=False, game_started=False, runtime_acceptance_complete=False)
    S.write(output/'source.json',record)
    return output/'source.json'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--stage-modules',action='store_true')
    args = parser.parse_args()
    print(prepare(args.state,args.output,args.root,args.stage_modules))
