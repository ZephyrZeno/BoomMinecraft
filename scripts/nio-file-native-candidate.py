"""Build an isolated source-verified Windows NIO diagnostic provider candidate.

Set nio_provider_mode to formal-selection and providers to the accepted provider
list to use the current batch's UFL2, JCLS and Boot native without old overlays.
Source selection and closure verification still reconstruct every supplied pack.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4
import winreg
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / '.boom'


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


S = module('nio_candidate_sources', 'runtime-provider-source.py')
R = module('nio_candidate_originals', 'verify-batch-frames.py')
A = module('nio_candidate_assembler', 'verify-batch-assembly.py')
IDS = module('nio_dispatcher_ids','nio-dispatcher-ids-source.py')
UNSAFE = 'jdk/internal/misc/Unsafe'
DISPATCH = 'sun/nio/fs/WindowsNativeDispatcher'
ATTRS = 'sun/nio/fs/WindowsFileAttributes'
EXCEPTION = 'sun/nio/fs/WindowsException'
REF = 'java/lang/ref/Reference'
SOFT = 'java/lang/ref/SoftReference'
NATIVES = [(UNSAFE, 'allocateMemory0', '(J)J', 0x102), (UNSAFE, 'freeMemory0', '(J)V', 0x102),
           (UNSAFE, 'copyMemory0', '(Ljava/lang/Object;JLjava/lang/Object;JJ)V', 0x102),
           (DISPATCH, 'GetFileAttributesEx0', '(JJ)V', 0x10a),
           (UNSAFE, 'getInt', '(Ljava/lang/Object;J)I', 0x101), (UNSAFE, 'getLong', '(Ljava/lang/Object;J)J', 0x101),
           (UNSAFE, 'putChar', '(Ljava/lang/Object;JC)V', 0x101),
           (DISPATCH,'initIDs','()V',0x10a),(REF,'get0','()Ljava/lang/Object;',0x102),
           ('java/lang/System','mapLibraryName','(Ljava/lang/String;)Ljava/lang/String;',0x109)]
JAVA = [(ATTRS, '<init>', '(IJJJJIIII)V'), (ATTRS, 'isRegularFile', '()Z'),
        (ATTRS, 'isSymbolicLink', '()Z'), (ATTRS, 'isDirectory', '()Z'), (ATTRS, 'isOther', '()Z'),
        (ATTRS, 'fromFileAttributeData', '(JI)Lsun/nio/fs/WindowsFileAttributes;'),
        (EXCEPTION, '<init>', '(I)V'), (EXCEPTION, 'lastError', '()I'), (EXCEPTION, 'fillInStackTrace','()Ljava/lang/Throwable;'),
        (UNSAFE, 'allocateMemory', '(J)J'), (UNSAFE, 'freeMemory', '(J)V'),
        ('java/lang/String', '<init>', '([C)V'), ('java/lang/String', 'toCharArray', '()[C'),
        ('java/lang/System','initPhase1','()V'),
        (SOFT,'<init>','(Ljava/lang/Object;)V'),(REF,'get','()Ljava/lang/Object;'),
        ('java/lang/String','length','()I'),('java/lang/IllegalArgumentException','<init>','(Ljava/lang/String;)V'),
        ('java/lang/Throwable','getMessage','()Ljava/lang/String;'),
        ('sun/nio/fs/WindowsPath','createFromNormalizedPath',
         '(Lsun/nio/fs/WindowsFileSystem;Ljava/lang/String;)Lsun/nio/fs/WindowsPath;'),
        ('java/nio/file/Files', 'isRegularFile', '(Ljava/nio/file/Path;[Ljava/nio/file/LinkOption;)Z')]


def contracts(config):
    batch, plan = (Path(config[k]).resolve(strict=True) for k in ('batch', 'plan'))
    summary = S.read(batch / 'summary.json')
    planned = S.read(plan / 'summary.json')
    S.check(planned['game_version']=='1.21.1' and S.read(batch / 'verification.json')['verified'] and
            summary['input_fingerprint'] == planned['input_fingerprint'],
            'Verified batch/source plan required')
    wanted = {s[0] for s in NATIVES + JAVA} | {'java/lang/Throwable','sun/nio/fs/WindowsFileSystem',
                                              'sun/nio/fs/WindowsFileSystemProvider'} | set(IDS.OWNERS)
    classes = {}
    with S.checked(planned['artifacts']['classes']).open(encoding='utf-8') as stream:
        for line in stream:
            c = json.loads(line)
            if c['name'] in wanted and c['origin']['loader'] == 'bootstrap':
                classes[c['name']] = c
    records = {}
    for name, c in classes.items():
        S.check(c['origin']['source_id'] == 'jdk:java.base' and not c['origin'].get('generated'), 'Original class required')
        n, raw = R.original_methods(S.original_class(summary, c))
        S.check(n == name and len(raw) == len(c['method_ids']), 'Original class method inventory differs')
        for ident, m in zip(c['method_ids'], raw):
            key = name, m['name'], m['descriptor']
            if key not in JAVA and not any(key == v[:3] for v in NATIVES):
                continue
            original = dict(owner=name, class_id=c['id'], class_sha256=c['origin']['sha256'], name=m['name'],
                            descriptor=m['descriptor'], access=m['access'], method=ident,
                            code_sha256=hashlib.sha256(m['code'][0]).hexdigest() if m['code'] is not None else None)
            S.check(key not in records, 'Ambiguous original source member')
            records[key] = original
    S.check(set(classes) == wanted and set(records) == set(JAVA) | {v[:3] for v in NATIVES},
            'Locked source declarations missing')
    natives = []
    for op, (owner, name, desc, access) in enumerate(NATIVES):
        m = records[owner, name, desc]
        S.check(m['access'] == access and m['code_sha256'] is None, 'Expected exact original native declaration')
        natives.append(dict(**m, operation=op))
    return summary, classes, natives, [records[k] for k in JAVA]


def run(command, directory, log):
    with (directory / log).open('wb') as stream:
        subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=1200, check=True)


def formal_providers(config):
    mode=config.get('nio_provider_mode','frozen-diagnostic')
    S.check(mode in ('frozen-diagnostic','formal-selection'),'Unknown NIO provider selection mode')
    if mode!='formal-selection':
        return None
    S.check(not any(config.get(k) for k in ('source_selection','nio_unsafe_carrier_test',
        'nio_unsafe_carrier_runtime','nio_boot_unnamed_candidate','nio_boot_unnamed_execution','nio_selection_providers')),
        'Formal selection must use the verified batch directly, without earlier candidate overlays')
    batch,plan=(Path(config[k]).resolve(strict=True) for k in ('batch','plan'))
    summary=S.read(batch/'summary.json')
    S.check(S.read(batch/'verification.json')['verified'] and summary['unsafe_fields']['abi']==2 and
            type(summary['class_literals'].get('bootstrap_unnamed_module_slot')) is int,
            'Formal NIO requires verified UFL2 and the normal bootstrap unnamed JCLS slot')
    paths=[Path(p).resolve(strict=True) for p in S.read(config['providers'])]
    S.check(len(paths)==len(set(paths)),'Duplicate formal provider manifests')
    if config.get('nio_provider_input_state'):
        state=S.read(S.checked(config['nio_provider_input_state']))
        S.check(state['status']=='accepted' and state['provider_count']==len(paths) and
                all(Path(state[k]).resolve()==Path(config[k]).resolve() for k in ('batch','plan','runtime','providers')) and
                state['batch_summary_sha256']==S.digest(batch/'summary.json')['sha256'] and
                state['batch_verification_sha256']==S.digest(batch/'verification.json')['sha256'] and
                state['runtime_sha256']==S.digest(Path(config['runtime'])/'boom-runtime.dll')['sha256'],
                'Formal provider input state differs from the source batch, runtime or list')
    result={}
    for path in paths:
        manifest=S.read(path)
        proof_path=path.with_name('verification.json')
        proof=S.read(proof_path)
        ref=dict(manifest=S.artifact(path),verification=S.artifact(proof_path))
        S.check(proof['verified'] and proof['provider_manifest_sha256']==ref['manifest']['digest']['sha256'] and
                proof['base_batch_summary_sha256']==S.digest(batch/'summary.json')['sha256'] and
                Path(manifest['base']['batch']).resolve()==batch and Path(manifest['base']['plan']).resolve()==plan and
                S.checked(manifest['base']['batch_summary'])==batch/'summary.json',
                'Formal provider lacks an accepted receipt for this exact batch: '+manifest['family'])
        S.checked(manifest['object'])
        S.check(manifest['family'] not in result,'Duplicate formal provider family')
        result[manifest['family']]=ref
    required={'normal-file-bootstrap-v1','cds-no-archive-v1','object-identity-v1','normal-constructors-v1',
              'class-flags-v1','normal-throwable-v1','normal-winnt-filesystem-v1',
              'normal-constructor-invocation-v1','normal-boot-unnamed-module-v1'}
    S.check(required<=set(result),'Formal provider list is missing a required NIO startup family')
    return result


def msvc():
    locator = Path(os.environ['ProgramFiles(x86)']) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    install = Path(subprocess.check_output([locator, '-utf8', '-latest', '-products', '*', '-requires',
                                           'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property',
                                           'installationPath']).decode('utf-8-sig').strip())
    version = (install / 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt').read_text().strip()
    return install / f'VC/Tools/MSVC/{version}/bin/Hostx64/x64'


def observed_classes(config,execution,provided_methods=()):
    if not execution:
        return set()
    execution=Path(execution).resolve(strict=True)
    S.check(execution.is_relative_to(ART),'Expected local source execution')
    report=S.read(execution)
    manifest=execution.parent/'candidate.json'
    candidate=S.read(manifest)
    S.check(report['candidate_manifest_sha256']==S.digest(manifest)['sha256'] and
            report['candidate_image_sha256']==S.digest(S.checked(candidate['image']))['sha256'] and
            report['source_Java_tail_succeeded'] and not report['game_started'],'Earlier execution receipt differs')
    selection=Path(candidate['selection_directory'])
    proof=S.read(S.checked(candidate['base_proof']))
    closure=S.read(selection/'closure.json')
    previous_batch=Path(closure['batch']).resolve(strict=True)
    S.check(Path(closure['plan']).resolve()==Path(config['plan']).resolve() and proof['verified'] and
            proof['closure_manifest_sha256']==S.digest(selection/'closure.json')['sha256'] and
            proof['diagnostic_manifest_sha256']==S.digest(selection/'diagnostic.json')['sha256'] and
            closure['source_batch_summary_sha256']==S.digest(previous_batch/'summary.json')['sha256'] and
            S.read(previous_batch/'summary.json')['input_fingerprint']==S.read(Path(config['batch'])/'summary.json')['input_fingerprint'],
            'Source execution belongs to another original plan or diagnostic selection')
    rows={r['id']:r for r in S.read(selection/'diagnostic.json')['rows']}
    existing=set(S.read(selection/'admit.json').get('additional_source_classes',[]))
    fresh=set()
    provided_next=False
    for stage in report['fresh_process_boundaries'].values():
        prep=stage.get('source_properties_preparation') or {}
        for fault in (stage.get('context_row'),prep.get('prior_global_diagnostic')):
            if not fault:
                continue
            original=rows[fault['id']]
            S.check(all(original.get(k)==fault.get(k) for k in ('symbol','category','method','binding')),
                    'Observed source diagnostic row differs')
            if original['category']==2 and original['method']['id'] not in candidate['new_normal_native_bindings']:
                if original['method']['id'] in provided_methods:
                    provided_next=True
                if any(candidate['source_classes'].get(owner)==original['class_id'] and original['method']['name']==name and
                       original['method']['descriptor']==desc for owner,name,desc,flags in NATIVES[7:]):
                    provided_next=True
            if fault['category'] not in (1,5):
                continue
            S.check(original['method']['assembly_emitted'] if original['category']==1 else
                    original['symbol']==f"boom_batch_initialize_{original['class_id']}",
                    'Observed gap is not an available original method or class initializer')
            fresh.add(original['class_id'])
    S.check(fresh-existing or provided_next,'No new emitted source gap or provider to admit')
    return existing|fresh


def prepare_selection(config_file,previous=None):
    config=S.read(config_file)
    formal=formal_providers(config)
    batch,plan=Path(config['batch']),Path(config['plan'])
    summary=S.read(batch/'summary.json')
    planned=S.read(plan/'summary.json')
    requests={}
    for spec in NATIVES+JAVA:
        requests.setdefault(spec[0],set()).add(spec[1])
    requests.update({
        'java/nio/file/Files':{'provider','isRegularFile'},'java/nio/file/spi/FileSystemProvider':{'readAttributesIfExists'},
        'java/lang/System':{'initPhase1','getProperties','getProperty','mapLibraryName'},
        'java/lang/Enum':None,'java/util/HashMap':None,'java/util/HashMap$Node':None,
        'java/lang/String':None,'java/lang/StringBuilder':None,'java/lang/AbstractStringBuilder':None,
        'java/lang/StringLatin1':None,'java/lang/Integer':{'toString','stringSize','getChars','hashCode'},
        'java/lang/CharacterDataLatin1':None,'java/lang/Character':{'digit','isDigit','codePointAt'},
        'sun/nio/cs/StandardCharsets':None,'sun/nio/cs/UTF_8':None,'sun/nio/cs/US_ASCII':None,
        'sun/nio/cs/StandardCharsets$Aliases':None,'sun/nio/cs/StandardCharsets$Cache':None,
        'sun/nio/cs/StandardCharsets$Classes':None,'sun/util/PreHashedMap':None,
        'sun/nio/cs/ISO_8859_1':None,'java/nio/charset/StandardCharsets':None,
        'java/lang/System$2':{'defineUnnamedModule','addEnableNativeAccess','getServicesCatalog','setServicesCatalog'},
        'java/lang/Class$1':None,
        'java/lang/reflect/Constructor':None,'java/lang/reflect/ReflectAccess':None,
        'java/lang/reflect/AccessibleObject':None,'java/lang/reflect/Executable':None,'jdk/internal/reflect/Reflection':None,
        'jdk/internal/reflect/ReflectionFactory':None,'jdk/internal/reflect/NativeConstructorAccessorImpl':None,
        'jdk/internal/reflect/DirectConstructorHandleAccessor$NativeAccessor':None,
        REF:{'get','<init>'},SOFT:{'get','<init>'},
        'jdk/internal/loader/BootLoader':None,'jdk/internal/loader/NativeLibraries':None,
        'jdk/internal/loader/ClassLoaderHelper':None,'jdk/internal/util/StaticProperty':None,
        'java/io/File':None,'java/io/WinNTFileSystem':None,
        'jdk/internal/loader/NativeLibraries$NativeLibraryImpl':None,'jdk/internal/loader/NativeLibraries$LibraryPaths':None,
        'java/util/HashMap$EntrySet':None,'java/util/HashMap$EntryIterator':None,'java/util/HashMap$HashIterator':None,
        'java/util/AbstractMap':{'<init>','putAll'},'java/util/Properties':None,
        'java/util/concurrent/ConcurrentHashMap':{'initTable','put','putVal','spread','casTabAt','setTabAt','tabAt','get',
            'addCount','sumCount','transfer','<init>','tableSizeFor'},
        'java/util/concurrent/ConcurrentHashMap$Node':None,'java/util/ImmutableCollections$Set12':None,
        'jdk/internal/util/SystemProps':None,'jdk/internal/util/SystemProps$Raw':None,
        'sun/nio/fs/WindowsFileSystem':{'provider'},'sun/nio/fs/WindowsFileSystemProvider':{'readAttributes','getFileAttributeView'},
        'sun/nio/fs/WindowsFileAttributeViews':{'createBasicView'},'sun/nio/fs/WindowsFileAttributeViews$Basic':{'<init>','readAttributes'},
        'sun/nio/fs/WindowsPath':{'createFromNormalizedPath','getFileSystem','getPathForWin32Calls','toWindowsPath','checkRead'},
        'sun/nio/fs/WindowsPathParser':None,'sun/nio/fs/WindowsPathParser$Result':None,'sun/nio/fs/WindowsPathType':None,
        'sun/nio/fs/WindowsFileAttributes':None,'sun/nio/fs/WindowsException':None,'sun/nio/fs/NativeBuffer':None,
        'sun/nio/fs/NativeBuffers':None,'sun/nio/fs/Util':{'followLinks'},
        DISPATCH:{'GetFileAttributesEx0','GetFileAttributesEx','asNativeBuffer','initIDs'},
        'java/io/FileInputStream':set(),'java/io/FileOutputStream':set(),'java/io/FileDescriptor':set(),
        'java/lang/StringUTF16':{'isBigEndian'},'java/lang/IllegalArgumentException':{'<init>'},
        'java/lang/Throwable':{'<init>','fillInStackTrace','getMessage'},
        'jdk/internal/misc/CDS':set(),'java/lang/Class':set(),'java/lang/Module':{'<init>'}})
    requests.update({owner:set() for owner in IDS.OWNERS})
    available={m['method'] for p in (formal or {}).values() for m in S.read(S.checked(p['manifest']))['methods']}
    additionally=observed_classes(config,previous,available)
    wanted={}
    with S.checked(planned['artifacts']['classes']).open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['id'] in additionally:
                S.check(row['origin']['loader']=='bootstrap' and row['origin']['source_id']=='jdk:java.base',
                        'Filesystem candidate source expansion is restricted to original java.base classes')
                requests[row['name']]=None
            if row['origin']['loader']=='bootstrap' and row['name'] in requests:
                wanted[f"classes/{row['id']:06}.json"]=row
    S.check(len(wanted)==len(requests),'Missing requested source selection types')
    admitted=set()
    for shard in summary['shards']:
        with zipfile.ZipFile(shard['zip']['path']) as archive:
            found=set(wanted).intersection(archive.namelist())
            if found:
                S.checked(shard['zip'])
            for name in found:
                source=wanted[name]
                compiled=json.loads(archive.read(name))
                S.check(compiled['source_sha256']==source['origin']['sha256'],'Original source shard differs')
                names=requests[source['name']]
                for m in compiled['methods']:
                    if (names is None or m['name'] in names) and (m['assembly_emitted'] or
                            any((source['name'],m['name'],m['descriptor'])==s[:3] for s in NATIVES[:4]+NATIVES[7:])):
                        admitted.add(m['id'])
    selection=ART/'nio-file-selections'/uuid4().hex
    selection.mkdir(parents=True)
    profile=selection/'admit.json'
    S.write(profile,dict(source_batch_summary_sha256=S.digest(batch/'summary.json')['sha256'],
                         admitted_classes=sorted(r['id'] for r in wanted.values()),admitted_methods=sorted(admitted),
                         additional_source_classes=sorted(additionally)))
    provider_args=[]
    for ref in config.get('nio_selection_providers',[]) if formal is None else [p['manifest'] for p in formal.values()]:
        path=S.checked(ref)
        S.check(formal is not None or S.read(path)['family'] in ('normal-constructors-v1','normal-constructor-invocation-v1'),
                'Unexpected NIO source-selection provider')
        provider_args+=['--provider-pack',path]
    run([sys.executable,ROOT/'scripts/prepare-diagnostic-closure.py',batch,'--plan',plan,'--output',selection,
         '--runtime',Path(config['runtime'])/'boom-runtime.dll','--entry','bootstrap:'+ATTRS+':isRegularFile:()Z',
         '--receiver-class','bootstrap:'+ATTRS,'--admit-profile',profile,*provider_args],selection,'source-selection.log')
    run([sys.executable,ROOT/'scripts/build-diagnostic-closure.py','--batch',batch,'--plan',plan,
         '--output',selection,'--runtime',config['runtime'],'--prepared-selection'],selection,'source-build.log')
    return selection


def referent_field(summary,classes):
    ref,soft=classes[REF],classes[SOFT]
    index=[i for i,f in enumerate(ref['fields']) if f==dict(name='referent',descriptor='Ljava/lang/Object;',access=2)]
    S.check(len(index)==1 and ref['access']==0x421,'Expected original private Reference.referent')
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as meta:
        [field]=[m for line in meta.open('fields.jsonl') if (m:=json.loads(line))['declaring_class']==ref['id'] and
                 m['declaring_field']==index[0]]
    offsets={v['receiver_class']:v['offset'] for v in field['rows']}
    S.check(field['reference'] and field['storage_bytes']==8 and {ref['id'],soft['id']} <= set(offsets),
            'Original inherited Reference.referent field domain is incomplete')
    return dict(map_id=field['id'],declaring_class=ref['id'],declaring_field=index[0],
                source_sha256=ref['origin']['sha256'],soft_reference=soft['id'],soft_offset=offsets[soft['id']])


def compose(classes, natives, java, fields, referent):
    constructor = next(m for m in java if m['owner'] == EXCEPTION)
    symbols = {k: classes[k]['id'] for k in (UNSAFE, DISPATCH, EXCEPTION, 'java/lang/Throwable')}
    replacements = {'NIO_EXCEPTION_CLASS': f'boom_class{symbols[EXCEPTION]}',
                    'NIO_EXCEPTION_LAYOUT': f'boom_layout{symbols[EXCEPTION]}',
                    'NIO_EXCEPTION_CTOR': f"boom_m{constructor['method']}",
                    'NIO_THROWABLE_TYPE': f"boom_t{symbols['java/lang/Throwable']}"}
    kernel = (ROOT / 'native/providers/nio_owned_buffers.asm.inc').read_text()
    error_path = (ROOT / 'native/providers/nio_windows_exception.asm.inc').read_text()
    for label, target in replacements.items():
        error_path = error_path.replace(label, target)
    data = {'boom_heap_ptr', 'boom_runtime_type_map', 'boom_trace_pool', *replacements.values()}
    procs = {'boom_class_ensure32', 'boom_object_new', 'boom_exception_set32', 'boom_trace_enter', 'boom_trace_leave',
             'boom_java_unsafe_memory', replacements['NIO_EXCEPTION_CTOR']}
    data -= procs
    data.add(f'boom_layout{symbols[UNSAFE]}')
    wrappers = []
    for m in natives[:4]:
        ident = m['method']
        data.update((f"boom_class{m['class_id']}", f'boom_trace_method{ident}'))
        wrappers += [f'PUBLIC boom_m{ident}\nPUBLIC boom_m{ident}_native\n',
                     R.native_adapter(ident, m['class_id'], 'boom_nio_buffer_pool', 'boom_nio_buffer_service', m['operation'])]
    field_table,field_symbols=IDS.data(fields)
    data.update(field_symbols)
    initializer=natives[7]
    ident=initializer['method']
    data.update((f"boom_class{initializer['class_id']}",f'boom_trace_method{ident}'))
    wrappers.extend((f'PUBLIC boom_m{ident}\nPUBLIC boom_m{ident}_native\n',
        R.native_adapter(ident,initializer['class_id'],'boom_nio_dispatcher_ids_pool','boom_nio_dispatcher_init_ids',0)))
    reader=natives[8]
    ident=reader['method']
    mapper=f"boom_field_map{referent['map_id']}"
    procs.add(mapper)
    data.update((f"boom_class{reader['class_id']}",f'boom_trace_method{ident}'))
    wrappers.extend((f'PUBLIC boom_m{ident}\nPUBLIC boom_m{ident}_native\n',
        R.native_adapter(ident,reader['class_id'],'source_referent_pool','boom_source_reference_get',0)))
    library=natives[9]
    ident=library['method']
    source_method=lambda owner,name:next(m for m in java if m['owner']==owner and m['name']==name)['method']
    error_class=classes['java/lang/IllegalArgumentException']['id']
    library_symbols={'LIB_NAME_STRING_LAYOUT':f"boom_layout{classes['java/lang/String']['id']}",
        'LIB_NAME_LENGTH':f"boom_m{source_method('java/lang/String','length')}",
        'LIB_NAME_CHARS':f"boom_m{source_method('java/lang/String','toCharArray')}",'LIB_NAME_ERROR_CLASS':f'boom_class{error_class}',
        'LIB_NAME_ERROR_LAYOUT':f'boom_layout{error_class}','LIB_NAME_THROWABLE_TYPE':replacements['NIO_THROWABLE_TYPE'],
        'LIB_NAME_ERROR_CTOR':f"boom_m{source_method('java/lang/IllegalArgumentException','<init>')}"}
    lib_name=(ROOT/'native/providers/win32_library_name.asm.inc').read_text()
    for label,target in library_symbols.items():
        lib_name=lib_name.replace(label,target)
    procs.update((library_symbols['LIB_NAME_CHARS'],library_symbols['LIB_NAME_LENGTH'],
        library_symbols['LIB_NAME_ERROR_CTOR'],'boom_java_property_copy'))
    data.update(set(library_symbols.values())-procs)
    data.update((f"boom_class{library['class_id']}",f'boom_trace_method{ident}','boom_java_platform_properties_pool'))
    wrappers.extend((f'PUBLIC boom_m{ident}\nPUBLIC boom_m{ident}_native\n',
        R.native_adapter(ident,library['class_id'],'boom_java_platform_properties_pool','boom_win32_library_name',0)))
    declaration = ''.join(f'EXTERN {s}:BYTE\n' for s in sorted(data))
    declaration += ''.join(f'EXTERN {s}:PROC\n' for s in sorted(procs))
    pool = ('.data\nALIGN 8\nPUBLIC boom_nio_buffer_pool\nboom_nio_buffer_pool DWORD 0424F494Eh,2\n'
            f' QWORD OFFSET boom_heap_ptr,OFFSET boom_layout{symbols[UNSAFE]},0,0,0,OFFSET nio_raise_windows_error\n')
    register=(ROOT/'native/providers/nio_dispatcher_ids.asm.inc').read_text()
    reader=(ROOT/'native/providers/reference_referent_read.asm.inc').read_text()
    reference_pool=(f'.const\nALIGN 8\nsource_referent_pool DWORD 054454752h,1\n QWORD OFFSET boom_heap_ptr,OFFSET {mapper}\n')
    return ('option casemap:none\n'+declaration+kernel+'\n'+error_path+'\n'+register+'\n'+reader+'\n'+lib_name+'\n'+reference_pool+field_table+pool+
            ''.join(wrappers)+'END\n')


def attach_offheap_domains(original, natives):
    # Only these three source-declared native trampolines acquire a null-base
    # owned-buffer domain. The original service handles every other input,
    # including the VM's separately owned logical thread ID counter.
    prefix = 'EXTERN boom_nio_buffer_service:PROC\nEXTERN boom_nio_buffer_pool:BYTE\n'
    for m in natives[4:7]:
        ident = m['method']
        label = f'boom_m{ident}_native'
        matches = list(re.finditer(rf'(?m)^{label} PROC\n lea r8,(\w+)\n mov r9d,(\d+)\n'
                                   rf' jmp boom_java_unsafe_memory\n{label} ENDP$', original))
        S.check(len(matches) == 1, 'Original Unsafe native trampoline differs')
        match = matches[0]
        pool, op = match.group(1, 2)
        body = f'''{label} PROC FRAME
 sub rsp,56
 .allocstack 56
 .endprolog
 test rcx,rcx
 jz {label}_old
 cmp DWORD PTR [rcx],0
 jne {label}_old
 test rdx,rdx
 jz {label}_old
 cmp QWORD PTR [rdx+8],0
 jne {label}_old
 mov QWORD PTR [rsp+32],rcx
 mov QWORD PTR [rsp+40],rdx
 lea r8,boom_nio_buffer_pool
 mov r9d,{m['operation']}
 call boom_nio_buffer_service
 mov rcx,QWORD PTR [rsp+32]
 cmp DWORD PTR [rcx],20
 jne {label}_done
 mov DWORD PTR [rcx],0
 mov rdx,QWORD PTR [rsp+40]
{label}_old:
 lea r8,{pool}
 mov r9d,{op}
 call boom_java_unsafe_memory
{label}_done:
 add rsp,56
 ret
{label} ENDP'''
        original = original[:match.start()] + body + original[match.end():]
    return original.replace('.code\n', prefix + '.code\n', 1)


def carrier_overlay(config,summary):
    if not config.get('nio_unsafe_carrier_test'):
        return Path(config['runtime']),{},None
    test_path=Path(config['nio_unsafe_carrier_test']).resolve(strict=True)
    runtime=Path(config['nio_unsafe_carrier_runtime']).resolve(strict=True)
    S.check(test_path.is_relative_to(ART) and runtime.is_relative_to(ART),'Expected project-owned carrier proof/runtime')
    test=S.read(test_path)
    batch=Path(test['batch']).resolve(strict=True)
    S.check(batch.is_relative_to(ART) and test['passed'] and test['original_Module_implAddEnableNativeAccess'] and
            test['runtime_sha256']==S.digest(runtime/'boom-runtime.dll')['sha256'],'Original Module carrier proof differs')
    manifest=batch/'unsafe-field-derivation.json'
    derived=S.read(manifest)
    receipt_file=batch/'unsafe-field-verification.json'
    receipt=S.read(receipt_file)
    S.check(test['field_derivation_sha256']==S.digest(manifest)['sha256'] and
            Path(derived['base_batch']).resolve()==Path(config['batch']).resolve() and
            Path(derived['plan']).resolve()==Path(config['plan']).resolve() and receipt['field_verification']['verified'] and
            receipt['summary']==derived['derivative'] and S.checked(receipt['summary'])==batch/'summary.json',
            'Carrier metadata does not derive from the selected original batch')
    changed=S.read(batch/'summary.json')
    field,old=changed['unsafe_fields'],summary['unsafe_fields']
    [row]=derived['replacements']
    S.check((old['abi'],field['abi'],row['unit'])==(1,2,2) and
            old['index']['digest']==field['index']['digest'] and row['object']==field['units'][2]['object'] and
            row['original_object']==old['units'][2]['object'],'Expected exactly the proven UFMP pool COFF')
    replacements={S.checked(row['original_object']):S.checked(row['object'])}
    return runtime,replacements,dict(derivation=S.artifact(manifest),field_verification=S.artifact(receipt_file),
        execution=S.artifact(test_path),replacement=row,full_derived_batch_verification_claimed=False)


def build(config_file, selection, out):
    out, selection = out.resolve(), selection.resolve(strict=True)
    S.check(out.is_relative_to(ART) and selection.is_relative_to(ART), 'Keep test images in project .boom')
    config = S.read(config_file)
    formal=formal_providers(config)
    out.mkdir(parents=True, exist_ok=False)
    summary, classes, natives, java = contracts(config)
    runtime,carrier_changes,carrier=carrier_overlay(config,summary)
    fields=IDS.index(summary,S.read(Path(config['plan'])/'summary.json'),classes,S)
    referent=referent_field(summary,classes)
    receipt = S.read(selection / 'selection-verification.json')
    closure = S.read(selection / 'closure.json')
    diagnostic = S.read(selection / 'diagnostic.json')
    S.check(receipt['verified'] and receipt['closure_manifest_sha256'] == S.digest(selection/'closure.json')['sha256'] and
            receipt['diagnostic_manifest_sha256'] == S.digest(selection/'diagnostic.json')['sha256'] and
            Path(closure['batch']).resolve() == Path(config['batch']).resolve() and
            Path(closure['plan']).resolve() == Path(config['plan']).resolve(), 'Selection proof differs')
    for m in java:
        selected = closure['selected_methods'].get(str(m['method']))
        S.check(selected and selected['code_sha256'] == m['code_sha256'] and selected['class_id'] == m['class_id'],
                'Required original Java body missing from selection: ' + m['name'])
    if formal is not None:
        S.check(list(formal.values())==closure.get('runtime_provider_packs'),
                'Verified source selection must carry the exact formal provider list')
    pack = next(S.read(p) for p in S.read(config['providers']) if S.read(p)['family'] == 'normal-winnt-filesystem-v1')
    overlay = S.read(S.checked(pack['frame_overlay']['manifest']))
    overlay_proof = S.read(S.checked(pack['frame_overlay']['verification']))
    S.check(overlay_proof['verified'] and overlay_proof['manifest_sha256']==pack['frame_overlay']['manifest']['digest']['sha256'],
            'Original native frame overlay proof is missing')
    frame_rows = {r['id']:r for r in overlay['source']['original_native_declarations']}
    for m in natives:
        r = frame_rows[m['method']]
        S.check(r['flags'] & 32 and not r['flags'] & 128 and all(r[k] == m[k] for k in
                ('class_id','class_sha256','name','descriptor','access')), 'Original framed native identity differs')
    frames = S.checked(overlay['object'])
    boot_ref=config.get('nio_boot_unnamed_candidate')
    boot=None
    formal_boot=None
    if boot_ref:
        boot=S.read(S.checked(boot_ref))
        info=boot['contract']
        declaration=info['native']
        boot_method=declaration['method']
        S.check(boot['family']=='normal-boot-unnamed-module-candidate' and not boot['shared_provider_registered'] and
                S.read(S.checked(boot['verification']))['verified'] and
                S.read(S.checked(boot['batch']))['input_fingerprint']==summary['input_fingerprint'] and
                S.checked(boot['plan'])==Path(config['plan'])/'summary.json' and
                boot['original_jcls_object']==summary['class_literals']['units'][0]['object'] and
                info['original_module_keys']==summary['class_literals']['modules'] and
                boot['added_key']==dict(id=len(info['original_module_keys']),loader=0,name=None) and
                boot['gc_roots_after']==info['root_cells']+1 and
                declaration['owner']=='jdk/internal/loader/BootLoader' and declaration['name']=='setBootLoaderUnnamedModule0' and
                all(frame_rows[boot_method][k]==declaration[k] for k in ('class_id','class_sha256','name','descriptor','access')),
                'Boot module source, base Class pool, or source native frame differs')
        for original in info['source_java']:
            entry=closure['selected_methods'].get(str(original['method']))
            S.check(entry and entry['code_sha256']==original['code_sha256'],'Boot module source body missing from candidate')
        S.check(A.coff_symbols(S.checked(boot['provider_object']),{'GetCurrentThreadId'})==
                (set(boot['exports']),set(boot['imports'])),'Boot module COFF symbols differ')
        if config.get('nio_boot_unnamed_execution'):
            btest=S.read(S.checked(config['nio_boot_unnamed_execution']))
            images=S.read(S.checked(btest['images']))
            S.check(btest['verified_Java_static_and_JCLS_publication'] and not btest['manually_installed_Module_oop'] and
                    images['control_link_matched_original_image'] and images['source']==boot_ref and
                    S.checked(images['runtime'])==runtime/'boom-runtime.dll','Boot module cold execution proof differs')
    if formal is not None:
        formal_boot_pack=S.read(S.checked(formal['normal-boot-unnamed-module-v1']['manifest']))
        formal_boot=S.read(S.checked(formal_boot_pack['boot_unnamed_metadata']))
        S.check(formal_boot['slot']==summary['class_literals']['bootstrap_unnamed_module_slot'] and
                formal_boot['strong_roots']==summary['class_literals']['root_cells'] and
                str(S.checked(formal_boot_pack['object'])) in closure['objects'],
                'Formal bootstrap module provider must use the existing verified JCLS pool')
        for original in formal_boot['original_java']:
            selected=closure['selected_methods'].get(str(original['method']))
            S.check(selected and selected['code_sha256']==original['code_sha256'],
                    'Formal bootstrap module original Java body is missing from the source selection')
    filesystem=classes['sun/nio/fs/WindowsFileSystem']
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        layout=next(row for line in stream if (row:=json.loads(line))['class_id']==filesystem['id'])
    field=module('nio_normal_field_reader','file-bootstrap-source.py').fields(filesystem,layout,[
        ('provider','Lsun/nio/fs/WindowsFileSystemProvider;',0x12,8,True)],S)[0]
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as archive:
        [link_array]=[row for line in archive.open('types.jsonl') if
                      (row:=json.loads(line))['name']=='[Ljava/nio/file/LinkOption;' and row['defining_loader']=='bootstrap']
    S.check(link_array['kind']==3,'Expected original LinkOption reference array')
    if formal is None:
        # Older diagnostic receipts remain reproducible with their frozen source
        # selection. Formal selections link the currently verified packs directly.
        prior = Path(config['source_selection'])
        prior_proof = S.read(prior/'selection-verification.json')
        S.check(prior_proof['verified'] and prior_proof['closure_manifest_sha256'] == S.digest(prior/'closure.json')['sha256'],
                'Earlier source selection was not verified')
        prior_closure=S.read(prior/'closure.json')
        accepted={S.read(S.checked(p['manifest']))['family']:p for p in prior_closure['runtime_provider_packs']}
    else:
        prior_closure=closure
        accepted=formal
    file_ref=accepted['normal-file-bootstrap-v1']
    cds_ref=accepted['cds-no-archive-v1']
    identity_ref=accepted['object-identity-v1']
    constructors_ref=accepted['normal-constructors-v1']
    class_flags_ref=accepted['class-flags-v1']
    throwable_ref=accepted['normal-throwable-v1']
    frame_ref=accepted['normal-winnt-filesystem-v1']
    frame_proof=S.read(S.checked(frame_ref['verification']))
    S.check(frame_proof['verified'] and frame_proof['provider_manifest_sha256']==frame_ref['manifest']['digest']['sha256']
            and pack==S.read(S.checked(frame_ref['manifest'])),'Frame overlay source pack differs from accepted selection')
    borrowed_objects=[]
    borrowed_names=set()
    prepared_refs={S.read(S.checked(record['manifest']))['family']:record
                   for record in closure.get('runtime_provider_packs',[])}
    for ref in (file_ref,cds_ref,identity_ref,constructors_ref,class_flags_ref,throwable_ref,frame_ref):
        previous=S.read(S.checked(ref['manifest']))
        proof=S.read(S.checked(ref['verification']))
        obj=S.checked(previous['object'])
        S.check(proof['verified'] and proof['provider_manifest_sha256']==ref['manifest']['digest']['sha256'] and
                proof['base_batch_summary_sha256']==S.digest(Path(config['batch'])/'summary.json')['sha256'] and
                str(obj) in prior_closure['objects'] and
                set(previous['required_class_ids'])<={s['class_id'] for s in closure['selected_classes']},
                'Frozen startup provider does not match the source closure: '+previous['family'])
        supplied=prepared_refs.get(previous['family'])
        if supplied:
            current=S.read(S.checked(supplied['manifest']))
            current_object=S.checked(current['object'])
            S.check(current['object']['digest']==previous['object']['digest'] and str(current_object) in closure['objects'] and
                    S.read(S.checked(supplied['verification']))['verified'],'Refreshed provider COFF differs from frozen source')
        else:
            borrowed_objects.append(obj)
        if formal is None:
            borrowed_names.update(f"boom_m{m['method']}" for m in previous['methods'])
    tools = msvc()
    def assemble(name, content=None, file=None):
        src = file or out / (name + '.asm')
        if content is not None:
            src.write_text(content, encoding='utf-8')
        obj = out / (name + '.obj')
        run([tools/'ml64.exe', '/nologo', '/c', f'/Fo{obj}', src], out, name + '.log')
        return obj
    provider = assemble('native-source-provider', compose(classes, natives, java,fields,referent))
    native_coff = A.coff_symbols(provider, {'LocalAlloc','LocalFree','AcquireSRWLockExclusive','ReleaseSRWLockExclusive',
                                          'AcquireSRWLockShared','ReleaseSRWLockShared'})
    S.check(all('boom_m'+str(m['method']) in native_coff[0] for m in natives[:4]+natives[7:]) and
            'boom_win32_raw_file_attributes' in native_coff[1], 'Candidate lacks a source native or its Win32 boundary')
    kernel = assemble('win32-query', file=ROOT/'native/runtime/win32_path_attributes.asm')
    [memory_unit] = summary['unsafe_memory']['units']
    memory = assemble('unsafe-extended-domains', attach_offheap_domains(S.checked(memory_unit['assembly']).read_text(), natives))
    admitted = {f"boom_m{m['method']}" for m in natives[:4]+natives[7:]}
    if boot:
        admitted.add(f'boom_m{boot_method}')
    gaps = {r['symbol']:r for r in diagnostic['rows'] if r['symbol'] in admitted}
    S.check(set(gaps) == admitted and all(r['category'] == 2 for r in gaps.values()), 'Missing original native stops')
    for row in diagnostic['rows']:
        if row['symbol'] in borrowed_names:
            S.check(row['category']==2, 'Unexpected frozen startup provider replacement')
            gaps[row['symbol']] = row
    stop_src = (selection/'diagnostic-stops.asm').read_text(encoding='utf-8')
    diagnostics=module('nio_source_context_stops','diagnostic-closure.py')
    S.check(stop_src==diagnostics.body(diagnostic['rows'],bool(closure.get('diagnostic_context_rows'))),
            'Original diagnostic rows or generated stop source changed')
    # The startup and filesystem contexts can encounter separate gaps in one
    # worker. Use the normal project sidecar to identify the exact row of each.
    stop_src=diagnostics.body(diagnostic['rows'],True)
    for name, row in gaps.items():
        text = (f"PUBLIC {name}\n{name} PROC\n lea rdx,boom_diagnostic_row{row['id']}\n"
                f" lea r8,boom_diagnostic_pool\n jmp boom_diagnostic_stop_context\n{name} ENDP\n")
        S.check(stop_src.count(text) == 1, 'Original diagnostic native stop body differs')
        stop_src = stop_src.replace(text, '', 1)
    stops = assemble('remaining-stops', stop_src)
    baseline_parts = S.read(selection/'assembly-provenance.json')
    S.check(receipt['verified_assembly_objects']['receipt_sha256']==S.digest(selection/'assembly-provenance.json')['sha256'],
            'Original selection object receipt changed')
    for u in baseline_parts['units']:
        S.checked(u['object'])
        S.checked(u['assembly'])
    replacements = {S.checked(memory_unit['object']):memory,**carrier_changes}
    original_frame=S.checked(summary['frames']['units'][0]['object'])
    if str(original_frame) in closure['objects']:
        replacements[original_frame]=frames
    else:
        S.check(formal is not None and str(frames) in closure['objects'] and
                closure['runtime_frame_overlay']['object']==overlay['object'],
                'Formal selection does not contain its verified native frame overlay')
    names = [m['method'] for m in java]
    exports = {'boom_nio_buffer_service','boom_nio_buffer_pool','boom_win32_path_attributes','boom_heap_ptr',
               'boom_nio_dispatcher_ids_pool'}
    if boot:
        replacements[S.checked(boot['original_jcls_object'])]=S.checked(boot['jcls_object'])
        borrowed_objects.append(S.checked(boot['provider_object']))
        exports.update(boot['exports'])
        exports.update(('boom_java_class_module_roots','boom_java_class_root_count',
                        f"boom_s{info['owner']}_{info['static_index']}"))
    if formal_boot:
        exports.update(('boom_java_class_module_roots','boom_java_class_root_count',
                        f"boom_s{formal_boot['owner']}_{formal_boot['static_field']}"))
    exports |= {f'boom_m{i}' for i in names}
    exports |= {f"boom_m{m['method']}{suffix}" for m in natives for suffix in ('','_native')}
    exports |= {f"boom_layout{classes[n]['id']}" for n in (UNSAFE,ATTRS,'java/lang/String','sun/nio/fs/WindowsPath',
               'sun/nio/fs/WindowsFileSystem','sun/nio/fs/WindowsFileSystemProvider',SOFT)}
    exports.add(f"boom_t{link_array['id']}")
    dll = out/'source-native-file.dll'
    symbols=set(closure['exports']) | exports | diagnostics.CONTEXT_EXPORTS
    original_inputs=[Path(p).resolve(strict=True) for p in closure['objects']]
    S.check(set(replacements)<=set(original_inputs) and all(p.is_relative_to(ART) for p in original_inputs),
            'Expected original frame and Unsafe COFF inputs')
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Microsoft\Windows Kits\Installed Roots') as key:
        sdk=Path(winreg.QueryValueEx(key,'KitsRoot10')[0])
    kernels=sorted((sdk/'Lib').glob('*/um/x64/kernel32.lib'),key=lambda p:tuple(map(int,p.parents[2].name.split('.'))))
    runtime_dll=runtime/'boom-runtime.dll'
    S.check(S.read(runtime/'runtime.json')['sha256']==S.digest(runtime_dll)['sha256'],'Assembly runtime changed')
    objects=[selection/'initialization-closure.obj',stops,*[replacements.get(p,p) for p in original_inputs],
             provider,kernel,*borrowed_objects,runtime/'boom-runtime.lib',kernels[-1].with_name('synchronization.lib'),kernels[-1]]
    jcls_object=S.checked(summary['class_literals']['units'][0]['object'])
    if formal is not None:
        S.check(jcls_object not in replacements and objects.count(jcls_object)==1,
                'Formal NIO must link the verified JCLS object exactly once without replacement')
    lines=['/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT','/BREPRO','/OUT:"'+str(dll)+'"']
    lines+=['"'+str(p)+'"' for p in objects]+['/EXPORT:'+s for s in sorted(symbols)]
    rsp = out/'link.rsp'
    rsp.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    run([tools/'link.exe','@'+str(rsp)],out,'link.log')
    report = dict(schema=1, family='windows-nio-owned-file-query-candidate', methods=natives,
                  original_Java=java, source_classes={n:c['id'] for n,c in classes.items()},
                  artifact_directory=str(out), selection_directory=str(selection), base_proof=S.artifact(selection/'selection-verification.json'),
                  provider=S.artifact(provider), kernel=S.artifact(kernel), extended_Unsafe=S.artifact(memory),
                  native_frame_overlay=S.artifact(frames),native_frame_provider=frame_ref,byte_order_provider=file_ref,
                  cds_provider=cds_ref,identity_provider=identity_ref,constructor_provider=constructors_ref,
                  class_flags_provider=class_flags_ref,throwable_provider=throwable_ref,winnt_provider=frame_ref,source_referent_field=referent,
                  image=S.artifact(dll),runtime=str(runtime),unsafe_carrier=carrier,boot_unnamed_candidate=boot_ref,
                  boot_unnamed_execution=config.get('nio_boot_unnamed_execution'),
                  runtime_dll=S.artifact(runtime_dll),kernel_source=S.artifact(ROOT/'native/runtime/win32_path_attributes.asm'),
                  source_batch=S.artifact(Path(config['batch'])/'summary.json'),
                  source_batch_verification=S.artifact(Path(config['batch'])/'verification.json'),
                  jcls_object=S.artifact(jcls_object),jcls_object_replaced=jcls_object in replacements,
                  link_response=S.artifact(rsp),
                  formal_provider_selection=list(formal.values()) if formal is not None else None,
                  formal_provider_input_state=config.get('nio_provider_input_state'),
                  boot_unnamed_provider=formal['normal-boot-unnamed-module-v1'] if formal is not None else None,
                  boot_unnamed_metadata=formal_boot_pack['boot_unnamed_metadata'] if formal_boot else None,
                  source_inputs=[S.artifact(ROOT/k) for k in ('native/providers/nio_owned_buffers.asm.inc',
                    'native/providers/nio_windows_exception.asm.inc','native/providers/nio_dispatcher_ids.asm.inc',
                    'native/providers/reference_referent_read.asm.inc','native/providers/win32_library_name.asm.inc',
                    'scripts/nio-dispatcher-ids-source.py','native/diagnostic/context_map.asm.inc',
                    'native/diagnostic/context_stop.asm.inc','scripts/nio-file-native-candidate.py',
                    'scripts/test-nio-file-native-candidate.py')],
                  generated_assembly=[S.artifact(out/n) for n in ('native-source-provider.asm','unsafe-extended-domains.asm',
                                                                  'remaining-stops.asm')],
                  filesystem_provider_field=field,link_option_array=link_array['id'],dispatcher_fields=fields,
                  owned_buffer_abi=2,allocation_header_bytes=32,
                  new_normal_native_bindings=sorted(int(n.removeprefix('boom_m')) for n in admitted),
                  extended_existing_Unsafe_domains=[m['method'] for m in natives[4:7]],
                  scope='separate development image',per_context_diagnostic_rows=True,
                  registered_in_shared_runtime=False,executed=False,game_started=False)
    S.write(out/'candidate.json',report)
    return out/'candidate.json'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ART/'pending-native-module-packages-v141.json')
    parser.add_argument('--selection',type=Path,help='Reuse a previously verified Windows NIO source selection')
    parser.add_argument('--follow-from',type=Path,help='Admit original Java classes identified in a verified prior candidate run')
    parser.add_argument('--output',type=Path,default=ART/'nio-file-candidates'/uuid4().hex)
    args=parser.parse_args()
    S.check(not (args.selection and args.follow_from),'Choose a verified selection or a prior observed execution')
    print(build(args.config,args.selection or prepare_selection(args.config,args.follow_from),args.output))
