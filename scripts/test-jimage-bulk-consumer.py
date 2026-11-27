"""Separate original-Java bulk consumer over a frozen successful NIO image.

The original runner is an explicit AST template, not silently monkeypatched.
Two edits are allowed: its first validator becomes the stricter combined
validator, and one separately reviewed bulk probe is inserted after getInt.
All original runtime, worker, GC-root and cleanup statements remain identical.
"""
import argparse
import ast
import copy
import ctypes as c
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('bulk_consumer_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


N=module('test-jimage-native-map');B=module('jimage-unsafe-copy-candidate');S=B.S
E=module('existing-source-selection');L=module('canonical-link-response');PFX=module('probe-native-provider-prefix')
M=module('vm-entry-source');D=module('diagnostic-closure');J=module('jimage-native-machine');H=module('diagnostic-leaf-machine')
ART=S.ART/'jimage-bulk-consumer';Q,U,P=c.c_uint64,c.c_uint32,c.c_void_p
Context=U*8
# Separately frozen NIO extension reader; images cannot choose a new verifier.
BASE_VERIFIER_SHA256='74d7463fb9c3217e10c865163d88940fcbc51a65cb45f3b55ffcef61ce10c35b'
ORIGINAL_NIO_RUNNER_SHA256='a21ed109f308cadf6eb53230d2ebdb26753b1a8b61ab7d1c0a2d527be5a44b91'
EXTENSION_TEMPLATE_SHA256='760521eb4c2676f3fe9e1da92592242b69b12a2943c52513d9fd63cf22fc18e5'
LEAF_HELPER_SHA256='86f0431d26ae36202d8a7e5ab219d6315a261a058070ebd2e0b784715f21a366'
_EXTENSION_READERS={}


def checked(row):return E.checked(row)


def hash_records(rows):
    return [S.artifact(checked(row)) for row in rows]


def combined_helpers():
    paths=[Path(__file__),*(Path(value.__file__) for value in (N,B,B.RB,B.C,B.O,S,E,L,PFX,M,D,J,H))]
    return [S.artifact(p) for p in dict.fromkeys(paths)]


def extension_reader(row):
    """Load only the independent frozen reader and its sealed template."""
    extension=row.get('native_extension',{})
    producer=extension.get('tool');S.check(isinstance(producer,dict),'Strict native extension reader required')
    tool=checked(producer)
    S.check(tool.parent==S.ART and tool.name.startswith('run-jimage-native-extension-') and tool.suffix=='.py' and
        producer in row['inputs'] and isinstance(BASE_VERIFIER_SHA256,str) and
        S.digest(tool)['sha256']==BASE_VERIFIER_SHA256,'Only the separately frozen NIO native extension reader may verify this base')
    for path,sha in [(Path(N.__file__),ORIGINAL_NIO_RUNNER_SHA256),(Path(H.__file__),LEAF_HELPER_SHA256),
                     (S.ART/'run-jimage-native-extension-v187-a.py',EXTENSION_TEMPLATE_SHA256)]:
        S.check(S.digest(path)['sha256']==sha,'Frozen native composition dependency changed')
        matches=[r for r in row['inputs'] if Path(r['path'])==path]
        S.check(matches and all(checked(r)==path for r in matches),'Frozen native reader dependency is not sealed')
    if BASE_VERIFIER_SHA256 not in _EXTENSION_READERS:
        spec=importlib.util.spec_from_file_location('bulk_strict_native_extension_'+BASE_VERIFIER_SHA256,tool)
        value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);_EXTENSION_READERS[BASE_VERIFIER_SHA256]=value
    return _EXTENSION_READERS[BASE_VERIFIER_SHA256]


def verified_base(path):
    """Run the complete Atomic/Scalar chain once before native execution."""
    path=Path(path).resolve();row=S.read(path)
    for record in row['inputs']:checked(record)
    reader=extension_reader(row);actual=reader.verify_images(path)
    producer=row['native_extension']['tool']
    S.check(actual['native_extension']['tool']==producer and Path(reader.T.__file__).resolve()==Path(N.__file__).resolve(),
        'The complete extension reader must preserve the frozen original NIO source')
    return actual


def current_stop(base):
    """Locate the actual current unit, never an earlier same-named input."""
    matches=[checked(r) for r in base['objects'] if Path(r['path']).name=='remaining-stops.obj']
    S.check(len(matches)==1,'One current ordered diagnostic stop object required');obj=matches[0];asm=obj.with_suffix('.asm')
    matches=[r for r in base['inputs'] if Path(r['path'])==asm]
    S.check(matches and all(checked(r)==asm for r in matches),'Current stop source must be sealed beside its actual object')
    return asm,obj


def copy_namespace_join(base,candidate):
    bridge=S.read(checked(base['bridge']));reader=extension_reader(base)
    join=reader.same_source_namespace(candidate['metadata']['input_state'],bridge['metadata']['input_state'])
    S.check(candidate['metadata']['bridge_candidate']==base['bridge'] and candidate['metadata']['runtime']==base['runtime'] and
        candidate['metadata']['base']==bridge['metadata']['base'],'Exact copy/bridge source base and physical runtime required')
    return join


def successful_execution(base_file,base):
    path=Path(base_file).with_name('execution.json');row=S.read(path)
    S.check(row['images']==S.artifact(base_file) and row['verified'] is True and row['complete_cleanup'] is True and
        row['scope']=='original_NativeImageBuffer_cold_initializer_lookup_and_JNI_JJ_constructor_component' and
        row['read_primitive_boundary']['passed'] is True and row['original_Java_fields_or_class_states_or_caches_host_written'] is False and
        base['unsafe_read_candidate'] is not None,'A successful frozen scalar/normal-source NIO baseline is required')
    return path,row


def import_lists(imports):return {dll:sorted(functions) for dll,functions in imports.items()}


# Historical callers used this name; new sealed compositions pin H directly.
leaf_stop_coff=H.leaf_stop_coff


def contract(base,copy_candidate):
    focused=S.read(checked(base['focused']));selection=Path(focused['source_selection_directory']);closure=S.read(checked(focused['source_manifest']));proof=S.read(checked(focused['source_selection']))
    S.check(proof['verified'] is True and proof['classes']==len(closure['selected_classes']) and proof['Java_methods']==len(closure['selected_methods']),'Actual source manifest/full proof counts differ')
    names={r['name']:r['class_id'] for r in closure['selected_classes']}
    specifications=[('java/nio/ByteBuffer','get','([B)Ljava/nio/ByteBuffer;'),('java/nio/ByteBuffer','get','([BII)Ljava/nio/ByteBuffer;'),
        ('java/nio/ByteBuffer','getArray','(I[BII)Ljava/nio/ByteBuffer;'),('java/nio/ByteBuffer','position','(I)Ljava/nio/ByteBuffer;'),
        ('java/nio/Buffer','position','()I'),('java/nio/Buffer','limit','()I'),('jdk/internal/misc/Unsafe','getUnsafe','()Ljdk/internal/misc/Unsafe;')]
    methods=[]
    for owner,name,desc in specifications:
        found=[(int(mid),row) for mid,row in closure['selected_methods'].items() if (row['class_id'],row['name'],row['descriptor'])==(names[owner],name,desc)]
        S.check(len(found)==1,'Selected original consumer API missing: '+str((owner,name,desc)));mid,row=found[0]
        methods.append(dict(owner=owner,name=name,descriptor=desc,method=mid,symbol='boom_m'+str(mid),class_sha256=row['source_sha256'],code_sha256=row['code_sha256']))
    for row in copy_candidate['metadata']['source']['original_Java']:
        actual=closure['selected_methods'].get(str(row['method']));S.check(actual and actual['class_id']==row['class_id'] and actual['source_sha256']==row['class_sha256'] and actual['code_sha256']==row['code_sha256'],'Original complete copy checks not selected')
    summary=S.read(Path(closure['batch'])/'summary.json');classes=[json.loads(line) for line in checked(focused['base']['source_classes']).open(encoding='utf-8')]
    I=B.C.I;cls=next(r for r in classes if r['name']=='java/nio/ByteBuffer' and r['origin']['loader']=='bootstrap');raw=I.Source(S.original_class(summary,cls));method=next(r for r in raw.methods if (r['name'],r['descriptor'])==('getArray','(I[BII)Ljava/nio/ByteBuffer;'))
    code=raw.code(method);instructions=list(I.stream(code['bytes']));constants=[(r,raw.symbol(r['operand']['Constant'])) for r in instructions if 'Constant' in r['operand']]
    limits=[(r,s['Long']) for r,s in constants if 'Long' in s];S.check(len(limits)==1,'Unique original array-copy threshold');literal,threshold=limits[0]
    compare=instructions[instructions.index(literal)+1:instructions.index(literal)+3];S.check([r['opcode'] for r in compare]==[0x94,0x9e] and threshold>=0,'Original large-array branch changed')
    native=copy_candidate['metadata']['source']['methods'][0];diag=S.read(selection/'diagnostic.json');rows=[r for r in diag['rows'] if r['symbol']=='boom_m'+str(native['method'])]
    S.check(len(rows)==1 and rows[0]['binding']['kind']=='native_declaration' and rows[0]['method']['code_sha256'] is None and rows[0]['source_sha256']==native['class_sha256'],'Exactly the original copy native diagnostic row required')
    return dict(selection=str(selection),source_proof=focused['source_selection'],classes=len(closure['selected_classes']),Java_methods=len(closure['selected_methods']),
        methods=methods,native=native,native_stop=rows[0],large_array_threshold=threshold,threshold_literal_pc=literal['pc'],original_Java_checks_whole=True),closure


def cheap_preflight(base_file,copy_file):
    """Check source/interface shape before any expensive model/frame reader.

    This performs no SourceV, assembler, linker, native loading or acceptance.
    The complete independent chain still runs before building or execution.
    """
    base_file,copy_file=Path(base_file).resolve(),Path(copy_file).resolve();base=S.read(base_file);candidate=S.read(copy_file)
    extension_reader(base);execution_file,_=successful_execution(base_file,base);join=copy_namespace_join(base,candidate)
    stop,obj=current_stop(base);info,closure=contract(base,candidate);context_rows=bool(closure.get('diagnostic_context_rows'));del closure
    target='boom_m'+str(info['native']['method']);stripped,removal=PFX.remove_stops(stop.read_bytes(),[info['native_stop']],context_rows,{target})
    observations={r['symbol'] for r in info['methods'] if r['name']!='getArray'}-set(base['exports'])
    S.check(D.pe_exports(checked(base['image']))==set(base['exports']),'Actual scalar baseline PE export set differs')
    definitions={name:[] for name in observations}
    for item in base['objects']:
        path=checked(item)
        for name in PFX.conflicting_public_definitions(path,observations):definitions[name].append(item)
    S.check(all(len(rows)==1 for rows in definitions.values()),'Selected original observation API is not a unique actual PUBLIC definition')
    return dict(verified=True,scope='metadata_source_and_interface_preflight_only_not_runtime_or_full_source_V',
        base_images=S.artifact(base_file),base_execution=S.artifact(execution_file),copy_candidate=S.artifact(copy_file),
        namespace_join=join,consumer_contract=info,diagnostic_context_rows=context_rows,
        current_stop_assembly=S.artifact(stop),current_stop_object=S.artifact(obj),
        planned_unique_stop_removal=removal,planned_remaining_source_sha256=hashlib.sha256(stripped).hexdigest(),
        extra_observation_exports=sorted(observations),unique_original_PUBLIC_definitions=definitions,
        reader=base['native_extension']['tool'],template_sha256=EXTENSION_TEMPLATE_SHA256,original_runner_sha256=ORIGINAL_NIO_RUNNER_SHA256,
        helper=S.artifact(__file__),expensive_native_source_frame_reader_executed=False,full_selection_reverified=False,
        assembler_or_linker_executed=False,Java_executed=False,accepted=False)


def build(base_file,copy_file,output,*,with_copy):
    helpers=combined_helpers();base_file,copy_file=Path(base_file).resolve(),Path(copy_file).resolve();output=Path(output).resolve()
    S.check(output.is_relative_to(ART) and not output.exists(),'Fresh consumer output required')
    preflight=cheap_preflight(base_file,copy_file);base=verified_base(base_file)
    execution_file,execution=successful_execution(base_file,base)
    runner_record=next(r for r in base['inputs'] if Path(r['path'])==Path(N.__file__).resolve());checked(runner_record)
    S.check(runner_record==S.artifact(N.__file__),'NIO runner changed after successful baseline');copy_proof=B.verify(copy_file);candidate=S.read(copy_file)
    namespace_join=copy_namespace_join(base,candidate)
    S.check(preflight['base_images']==S.artifact(base_file) and preflight['copy_candidate']==S.artifact(copy_file) and namespace_join==preflight['namespace_join'],
        'Low-cost source/interface inputs changed during complete verification')
    info=preflight['consumer_contract'];first=hash_records(base['inputs']);output.mkdir(parents=True);S.write(output/'cheap-preflight.json',preflight)
    # Independently reproduce the complete map/library COFF, including symbols
    # and aux records, in addition to their source receipt checks.
    machine_dir=S.ART/'jimage-native-map/bulk-machine-checks'/uuid4().hex
    proofs={kind:S.artifact(J.verify(checked(base[key]),kind,machine_dir/kind)) for kind,key in [('map','bridge'),('library','library')]}
    objects=[checked(r) for r in base['objects']];libraries=[checked(r) for r in base['libraries']];removal=None;generated=[];derived_stop=None
    if with_copy:
        stop,old_obj=current_stop(base);S.check(objects.count(old_obj)==1,'One sealed current stop unit required')
        target='boom_m'+str(info['native']['method']);raw=stop.read_bytes();remaining,removal=PFX.remove_stops(raw,[info['native_stop']],preflight['diagnostic_context_rows'],{target})
        S.check(removal==preflight['planned_unique_stop_removal'] and hashlib.sha256(remaining).hexdigest()==preflight['planned_remaining_source_sha256'],
            'Native stop derivation differs from the prior exact-source preflight')
        asm,obj=output/'remaining-stops.asm',output/'remaining-stops.obj';asm.write_bytes(remaining);B.RB.assemble(asm,obj,B.checked(candidate['assembler']),output/'assembler.log')
        old_defs,old_refs=B.RB.A.coff_symbols(old_obj);S.check(B.RB.A.coff_symbols(obj)==(old_defs-{target},old_refs),'Only the original native fail-only definition may change')
        derived_stop=dict(original_assembly=S.artifact(stop),original_object=S.artifact(old_obj),assembly=S.artifact(asm),object=S.artifact(obj))
        objects=[obj if p==old_obj else p for p in objects];extra=[B.checked(candidate['object']),B.checked(candidate['core_object'])]
        definitions=[B.RB.A.coff_symbols(p,{'AcquireSRWLockShared','ReleaseSRWLockShared'})[0] for p in extra];names=set().union(*definitions)
        S.check(sum(map(len,definitions))==len(names) and not any(PFX.conflicting_public_definitions(p,names) for p in objects),
            'Bulk native/core collides with retained source or each other');objects+=extra;generated=[S.artifact(asm),S.artifact(obj)]
    # These are exports of already-selected original Code, not new code/roots.
    original_exports=set(base['exports']);observations={r['symbol'] for r in info['methods'] if r['name']!='getArray'}-original_exports
    for symbol in observations:
        definitions=[p for p in objects if PFX.conflicting_public_definitions(p,{symbol})];S.check(len(definitions)==1,'One actual original PUBLIC definition required for '+symbol)
    exports=original_exports|observations
    if with_copy:exports|=B.C.assembly(candidate['metadata']['source'])[1]
    image,rsp=output/'jimage-bulk-consumer.dll',output/'link.rsp';rsp.write_text('\n'.join([*L.PREFIXES['diagnostic'],'/OUT:"'+str(image)+'"',*['"'+str(p)+'"' for p in objects+libraries],*['/EXPORT:'+n for n in sorted(exports)]])+'\n',encoding='utf-8',newline='\n')
    L.verify(rsp,profile='diagnostic',output=image,objects=objects,library_choices=[libraries],exports=exports)
    with (output/'link.log').open('xb') as log:r=subprocess.run([str(B.checked(candidate['linker'])),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT)
    S.check(r.returncode==0,'Owned normal-Java bulk image link failed');S.check(D.pe_exports(image)==exports,'Actual consumer exports differ');pe=M.pe(image)
    S.check(import_lists(pe['imports'])==import_lists(base['imports']),'Consumer PE changed per-DLL import functions/multiplicities')
    second=hash_records(base['inputs']);S.check(first==second,'Original source/COFF/runner bytes changed during native-only derivation')
    S.check(helpers==combined_helpers(),'Combined harness/helper sources changed during native derivation')
    row=copy.deepcopy(base);row.update(scope='original_Java_bulk_consumer_with_explicit_native_only_derivation',base_images=S.artifact(base_file),base_execution=S.artifact(execution_file),
        image=S.artifact(image),response=S.artifact(rsp),objects=[S.artifact(p) for p in objects],libraries=[S.artifact(p) for p in libraries],exports=sorted(exports),imports=pe['imports'],
        base_extension_verifier=base['native_extension']['tool'],leaf_machine_helper=S.artifact(H.__file__),
        copy_source_namespace_join=namespace_join,
        cheap_preflight=S.artifact(output/'cheap-preflight.json'),
        combined_helper_inputs=helpers,
        native_copy_enabled=with_copy,copy_candidate=S.artifact(copy_file),copy_source_proof=copy_proof,consumer_contract=info,extra_observation_exports=sorted(observations),
        unique_native_stop_removal=removal,additional_native_declarations=1 if with_copy else 0,full_nondebug_candidate_machine=proofs,
        derived_stop=derived_stop,
        original_source_inputs_before=first,original_source_inputs_after=second,original_Java_and_metadata_COFF_preserved=True,
        original_gc_root_spans_preserved=True,source_selection_reverified=False,baseline_expected_native_gap=not with_copy)
    paths=[*objects,*libraries,base_file,execution_file,copy_file,copy_file.with_name('verification.json'),Path(__file__),Path(N.__file__),Path(J.__file__),Path(H.__file__),checked(base['native_extension']['tool']),output/'cheap-preflight.json',rsp,image]
    paths += [B.checked(candidate[key]) for key in ('assembly','object','core_assembly','core_object','image','response','assembler','linker','kernel32','runtime_library')]
    paths += [checked(r) for r in candidate['metadata']['sources'].values()]
    row['inputs']=base['inputs']+[S.artifact(p) for p in dict.fromkeys(paths)]+generated+[proofs['map'],proofs['library']]+helpers
    snapshot=output/'original-nio-runner.py';snapshot.write_bytes(Path(N.__file__).read_bytes());row['runner_snapshot']=S.artifact(snapshot);row['inputs'].append(row['runner_snapshot'])
    S.check(row['quiescent_root_spans']==base['quiescent_root_spans'],'No roots may be fabricated for the additional test')
    path=output/'images.json';S.write(path,row);return path


def bulk_verified_images(path):
    row=S.read(path);S.check(row['scope']=='original_Java_bulk_consumer_with_explicit_native_only_derivation','Exact combined scope required');base=verified_base(checked(row['base_images']))
    for r in row['inputs']:checked(r)
    S.check(row['combined_helper_inputs']==combined_helpers(),'Current combined verifier/harness helpers changed')
    S.check(row['base_extension_verifier']==base['native_extension']['tool'] and row['leaf_machine_helper']==S.artifact(H.__file__),'Frozen extension/leaf reader changed')
    execution_file,_=successful_execution(checked(row['base_images']),base)
    S.check(row['base_execution']==S.artifact(execution_file),'Original normal-source baseline lost its bound result')
    actual=B.verify(checked(row['copy_candidate']));S.check(actual==row['copy_source_proof'],'Current complete copy source/machine proof changed')
    S.check(copy_namespace_join(base,S.read(checked(row['copy_candidate'])))==row['copy_source_namespace_join'],
        'Exact accepted/pending copy/bridge source namespace join changed')
    for kind,artifact in row['full_nondebug_candidate_machine'].items():
        key='bridge' if kind=='map' else 'library';proof=S.read(checked(artifact));S.check(proof['verified'] is True and proof['kind']==kind and proof['candidate']==base[key] and proof['all_code_data_relocations_and_unwind_verified'] is True,'Full map/library machine proof missing')
        for r in proof['inputs']:checked(r)
        checked(proof['canonical_assembly']);checked(proof['canonical_object'])
        candidate=S.read(checked(base[key]));S.check(B.O.normalized_coff(checked(candidate['object']))==proof['normalized']==B.O.normalized_coff(checked(proof['canonical_object'])),'Actual complete map/library COFF proof differs')
    S.check(row['quiescent_root_spans']==base['quiescent_root_spans'] and row['original_source_inputs_before']==row['original_source_inputs_after']==hash_records(base['inputs']),
        'Original full-source inputs/root banks changed')
    info,_=contract(base,S.read(checked(row['copy_candidate'])));S.check(info==row['consumer_contract'],'Original consumer Code/source contract differs')
    preflight=S.read(checked(row['cheap_preflight']))
    S.check(preflight['verified'] is True and preflight['scope']=='metadata_source_and_interface_preflight_only_not_runtime_or_full_source_V' and
        preflight['consumer_contract']==info and preflight['base_images']==row['base_images'] and preflight['copy_candidate']==row['copy_candidate'] and
        preflight['namespace_join']==row['copy_source_namespace_join'] and preflight['helper']==S.artifact(__file__) and
        all(preflight[k] is False for k in ('expensive_native_source_frame_reader_executed','full_selection_reverified','assembler_or_linker_executed','Java_executed','accepted')),
        'Exact low-cost preflight scope/input receipt changed')
    expected=[checked(r) for r in base['objects']];copy_candidate=S.read(checked(row['copy_candidate']));exports=set(base['exports']);observations={r['symbol'] for r in info['methods'] if r['name']!='getArray'}-exports
    S.check(row['extra_observation_exports']==sorted(observations),'Observation exports differ from exact original selected APIs')
    exports|=observations
    if row['native_copy_enabled']:
        stop=row['derived_stop'];old_asm,old_obj=current_stop(base)
        S.check(stop['original_assembly']==S.artifact(old_asm) and stop['original_object']==S.artifact(old_obj) and expected.count(old_obj)==1,'Original unique stop unit changed')
        focused=S.read(checked(base['focused']));closure=S.read(checked(focused['source_manifest']));target='boom_m'+str(info['native']['method'])
        source,removal=PFX.remove_stops(old_asm.read_bytes(),[info['native_stop']],bool(closure.get('diagnostic_context_rows')),{target})
        S.check(checked(stop['assembly']).read_bytes()==source and row['unique_native_stop_removal']==removal,'A second stop or any row/Java source byte changed')
        # This is a new native-only assembly, so reproduce its complete actual
        # COFF. The unchanged 70k-method source selection is never rebuilt.
        scratch=ART/'stop-machine-checks'/uuid4().hex;scratch.mkdir(parents=True);asm,obj=scratch/'canonical.asm',scratch/'canonical.obj';asm.write_bytes(source)
        B.RB.assemble(asm,obj,B.checked(copy_candidate['assembler']),scratch/'assembler.log')
        leaf=H.verify(checked(stop['object']),obj,source);leaf['canonical_assembly']=S.artifact(asm)
        S.write(scratch/'verification.json',leaf)
        row['_current_stop_machine_verification']=S.artifact(scratch/'verification.json')
        expected=[checked(stop['object']) if p==old_obj else p for p in expected]+[B.checked(copy_candidate['object']),B.checked(copy_candidate['core_object'])]
        exports|=B.C.assembly(copy_candidate['metadata']['source'])[1]
        S.check(row['additional_native_declarations']==1,'Exactly one additional native declaration required')
    else:S.check(row['derived_stop'] is None and row['unique_native_stop_removal'] is None and row['additional_native_declarations']==0,'Diagnostic baseline must keep every original object')
    objects=[checked(r) for r in row['objects']];libraries=[checked(r) for r in row['libraries']]
    S.check(objects==expected and row['libraries']==base['libraries'] and set(row['exports'])==exports,'Actual ordered COFF/library/export contract changed')
    L.verify(checked(row['response']),profile='diagnostic',output=checked(row['image']),objects=objects,library_choices=[libraries],exports=row['exports'])
    S.check(D.pe_exports(checked(row['image']))==set(row['exports']) and M.pe(checked(row['image']))['imports']==row['imports'] and
        import_lists(row['imports'])==import_lists(base['imports']),'Actual combined PE exports or per-DLL import functions/multiplicities changed')
    return row


def bulk_probe(record,rt,image,heap,buffer,path,call):
    info=record['consumer_contract'];out=Path(record['image']['path']).parent;members={(r['owner'],r['name'],r['descriptor']):r['method'] for r in info['methods']}
    def java(owner,name,desc,args,**options):return call(members[owner,name,desc],args,**options)
    def position(at):
        value,_=java('java/nio/ByteBuffer','position','(I)Ljava/nio/ByteBuffer;',[buffer,at]);S.check(value==buffer,'Whole original position setter did not return this')
    def read_position():return java('java/nio/Buffer','position','()I',[buffer])[0]
    whole=path.read_bytes();before_position=read_position();limit=java('java/nio/Buffer','limit','()I',[buffer])[0];S.check(before_position==0 and limit==len(whole),'Real original JNI buffer shape changed')
    cases=[(0,0),(0,1),(1,2),(2,info['large_array_threshold']),(0,info['large_array_threshold']+1),(27,512),(65536,65536),(len(whole)-4096,4096)];observations=[]
    for at,n in cases:
        position(at);ctx=Context();array=N.proc(rt,'boom_array_new',P,P,c.c_int,U,P)(heap,n,8,ctx);S.check(array and not ctx[0],'Real normal Java byte array allocation failed')
        returned,_=java('java/nio/ByteBuffer','get','([B)Ljava/nio/ByteBuffer;',[buffer,array])
        S.check(returned==buffer and c.string_at(array,n)==whole[at:at+n] and read_position()==at+n,'Whole original Java bulk get data/position differs')
        observations.append(dict(source_offset=at,bytes=n,output_sha256=hashlib.sha256(c.string_at(array,n)).hexdigest(),source_large_copy_branch=n>info['large_array_threshold']))
    position(64);ctx=Context();array=N.proc(rt,'boom_array_new',P,P,c.c_int,U,P)(heap,19,8,ctx);S.check(array and not ctx[0],'Normal offset-destination byte[] allocation')
    c.memset(array,0xa5,19);returned,_=java('java/nio/ByteBuffer','get','([BII)Ljava/nio/ByteBuffer;',[buffer,array,3,13]);S.check(returned==buffer and c.string_at(array,19)==b'\xa5'*3+whole[64:77]+b'\xa5'*3 and read_position()==77,'Original nonzero destination offset semantics differ')
    unsafe,_=java('jdk/internal/misc/Unsafe','getUnsafe','()Ljdk/internal/misc/Unsafe;',[]);pending=Context(16,17,18,0,19,20,21,22);saved=bytes(pending)
    call(info['native']['method'],[unsafe,0,0,array,0,13],check=False,context=pending);S.check(bytes(pending)==saved,'Normal native Frame8 adapter changed pending Context')
    position(before_position);S.check(read_position()==before_position and java('java/nio/Buffer','limit','()I',[buffer])[0]==limit,'Only original Java setters may restore position; limit must remain unchanged')
    result=dict(verified=True,scope='actual_original_ByteBuffer_bulk_Java_consumer_and_original_checks',original_get_map_receiver_reused=True,
        observations=observations,original_get_array_and_ScopedMemory_and_Unsafe_checks_selected=True,large_array_threshold=info['large_array_threshold'],
        original_native_Frame8_executed=True,normal_Unsafe_receiver_obtained_by_original_getUnsafe=True,pending_Context_all_32_bytes_unchanged=True,
        normal_byte_arrays_allocated_by_original_ASM=True,Java_fields_or_class_states_or_metadata_or_root_banks_host_written=False,original_position_restored_by_Java=True,
        complete_stop_COFF_verification=record.get('_current_stop_machine_verification'))
    S.write(out/'bulk-observations.json',result);return result


def derived_execute(images_file):
    images_file=Path(images_file).resolve();entry_artifact=S.artifact(images_file);record=S.read(images_file);out=images_file.parent
    snapshot=checked(record['runner_snapshot'])
    S.check(S.digest(snapshot)==S.digest(N.__file__) and S.digest(snapshot)['sha256']==ORIGINAL_NIO_RUNNER_SHA256,
        'Only the separately frozen original NIO execute template may be compiled')
    # The complete combined verifier remains the first statement of the
    # derived lifecycle. Preparing its locked AST does not execute the native
    # runtime, and avoids repeating that whole verifier before the first call.
    source=snapshot.read_text(encoding='utf-8');original=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='execute');changed=copy.deepcopy(original)
    first=changed.body[0];S.check(isinstance(first,ast.Assign) and isinstance(first.value,ast.Call) and isinstance(first.value.func,ast.Name) and first.value.func.id=='verified_images','Frozen runner first-validator insertion point changed');first.value.func.id='bulk_verified_images'
    tries=[n for n in changed.body if isinstance(n,ast.Try)];S.check(len(tries)==1,'One original runtime lifecycle try/finally required');body=tries[0].body
    targets=[i for i,n in enumerate(body) if isinstance(n,ast.For) and isinstance(n.target,ast.Tuple) and [x.id for x in n.target.elts]==['args','wanted']];S.check(len(targets)==1,'One explicit post-getInt insertion point required')
    addition=ast.parse("bulk_probe(record,rt,image,heap,successful[0]['buffer'],path,call)").body[0];body.insert(targets[0],addition)
    restored=copy.deepcopy(changed);restored.body[0].value.func.id='verified_images';runtime_try=next(n for n in restored.body if isinstance(n,ast.Try));del runtime_try.body[targets[0]]
    S.check(ast.dump(restored,include_attributes=False)==ast.dump(original,include_attributes=False),'Original runtime/GC/cleanup body changed beyond two declared edits')
    changed.name='bulk_component_execute';ast.fix_missing_locations(changed);generated=ast.unparse(changed)+'\n';generated_file=out/'derived-execute.py';generated_file.write_text(generated,encoding='utf-8',newline='\n')
    evidence=dict(scope='explicit_host_test_template_derivation_not_original_runner_claim',original_runner=record['runner_snapshot'],new_runner=S.artifact(__file__),derived_source=S.artifact(generated_file),
        edits=['first call uses strict combined verifier','one post-getInt bulk_probe call','host function renamed'],all_other_runtime_workers_GC_roots_cleanup_AST_identical=True,
        original_AST_sha256=hashlib.sha256(ast.dump(original,include_attributes=False).encode()).hexdigest(),restored_AST_sha256=hashlib.sha256(ast.dump(restored,include_attributes=False).encode()).hexdigest())
    S.write(out/'AST-equivalence.json',evidence);namespace=dict(N.__dict__);namespace.update(bulk_verified_images=bulk_verified_images,bulk_probe=bulk_probe)
    exec(compile(ast.Module(body=[changed],type_ignores=[]),str(generated_file),'exec'),namespace);result=namespace['bulk_component_execute'](images_file);old=S.read(result)
    final=dict(verified=old['verified'] is True and (out/'bulk-observations.json').exists() and S.read(out/'bulk-observations.json')['verified'] is True,
        scope='unregistered_original_Java_bulk_consumer_combined_component',images=S.artifact(images_file),complete_cleanup=old['complete_cleanup'],
        original_component_execution=S.artifact(result),AST_equivalence=S.artifact(out/'AST-equivalence.json'),bulk_observations=S.artifact(out/'bulk-observations.json') if (out/'bulk-observations.json').exists() else None,
        baseline_expected_native_gap=record['baseline_expected_native_gap'],original_Java_or_metadata_changed=False,full_selection_reverified=False,registered=False,game_started=False)
    if record['baseline_expected_native_gap']:
        failure=S.read(out/'first-failure.json') if (out/'first-failure.json').exists() else None;final['actual_baseline_frontier']=failure
        final['expected_copy_native_stop_observed']=bool(failure and failure.get('row')==record['consumer_contract']['native_stop'] and failure['context'][0]==0xb001)
    for row in record['inputs']:checked(row)
    S.check(S.artifact(images_file)==entry_artifact,'Combined images manifest changed during execution')
    S.write(out/'bulk-execution.json',final);return out/'bulk-execution.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('preflight','build-baseline','build-copy','run'));p.add_argument('--base-images',type=Path);p.add_argument('--copy',type=Path);p.add_argument('--output',type=Path);p.add_argument('--images',type=Path);a=p.parse_args()
    if a.action=='run' and a.images is None:p.error('run requires --images')
    if a.action!='run' and any(value is None for value in (a.base_images,a.copy,a.output)):p.error('preflight/build require --base-images, --copy and --output')
    if a.action=='run':
        result=derived_execute(a.images.resolve());row=S.read(result);print(result)
        S.check(row['complete_cleanup'] is True and (row.get('expected_copy_native_stop_observed') is True if row['baseline_expected_native_gap'] else row['verified'] is True),
            'Original Java consumer failed outside its explicit baseline/positive scope; evidence preserved')
    elif a.action=='preflight':
        output=a.output.resolve();S.check(output.is_relative_to(ART) and not output.exists(),'Fresh preflight output required')
        proof=cheap_preflight(a.base_images,a.copy);output.mkdir(parents=True);S.write(output/'verification.json',proof);print(output/'verification.json')
    else:print(build(a.base_images,a.copy,a.output,with_copy=a.action=='build-copy'))
