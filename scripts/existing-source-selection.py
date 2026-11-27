"""Seal an independently reverified source selection for separate native overlays.

The envelope preserves the original selection directory and every original
Java/provider object. Unregistered native code/data are separate later inputs;
neither is claimed as part of this original-source verification.
"""
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import sys
from threading import Lock,local


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('existing_selection_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


F=module('formal-provider-selection');S=F.S
L=module('canonical-link-response')
SCOPE='immutable_existing_current_source_selection_for_separate_unregistered_native_overlay'


def runtime_file(state):
    path=Path(state['runtime'])
    return path/'boom-runtime.dll' if path.is_dir() else path


def checked(record):
    """Accept the two actual input schemas; retain all advertised hash checks."""
    expected=record.get('digest',record)
    S.check(type(expected.get('size')) is int and isinstance(expected.get('sha256'),str),
        'Expected a nested or flat size/SHA256 artifact')
    normalized=dict(path=record['path'],digest={k:expected[k] for k in ('size','sha256')})
    path=F.checked(normalized)
    if 'sha1' in expected:
        with path.open('rb') as stream:
            S.check(hashlib.file_digest(stream,'sha1').hexdigest()==expected['sha1'],'Legacy source SHA1 changed')
    return path


class ReadInputs:
    """Capture actual verifier reads and imported source, including flat-input paths.

    Hash each file before its first read and again before publishing. The audit
    hook remains inactive after this invocation. Fresh verifier scratch outputs
    are excluded; overwriting an existing consumed input is rejected.
    """
    def __init__(self,seal):
        self.seal=seal;self.active=False;self.busy=local();self.lock=Lock();self.seen=set();self.created=set()

    def record(self,path):
        if isinstance(path,int):return
        text=os.fsdecode(path)
        if text.startswith('<') and text.endswith('>'):return
        path=Path(text).resolve()
        if path in self.created or not path.is_file():return
        with self.lock:
            if path not in self.seen:self.seal(path);self.seen.add(path)

    def hook(self,event,args):
        if not self.active or getattr(self.busy,'value',False):return
        self.busy.value=True
        try:
            if event=='open':
                path,mode,flags=args
                if isinstance(path,int):return
                path=Path(os.fsdecode(path)).resolve()
                writing=bool(flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
                if writing:
                    S.check(path not in self.seen,'Source verifier overwrote a consumed input: '+str(path))
                    if not path.exists():self.created.add(path)
                else:self.record(path)
            elif event=='exec':self.record(args[0].co_filename)
        finally:self.busy.value=False

    def __enter__(self):
        sys.addaudithook(self.hook);self.active=True;return self

    def __exit__(self,*_):self.active=False


def context(state_file,selection):
    state,values,paths=F.state_inputs(state_file)
    identity,_,_=S.base(values['batch'],values['plan'])
    selection=Path(selection).resolve()
    S.check(selection.is_relative_to(S.ART),'Original source selection must stay in project artifacts')
    closure=S.read(selection/'closure.json');diagnostic=S.read(selection/'diagnostic.json')
    proof=S.read(selection/'selection-verification.json')
    S.check(proof['verified'] is True and proof['scope']=='selected_original_source_with_development_fail_stops_only' and
        Path(closure['batch']).resolve()==values['batch'] and Path(closure['plan']).resolve()==values['plan'] and
        closure['source_batch_summary_sha256']==identity['batch_summary']['digest']['sha256'],
        'Existing source selection/base identity differs from the current state')
    S.check(state['batch_summary_sha256']==identity['batch_summary']['digest']['sha256'] and
        state['batch_verification_sha256']==identity['base_verification']['digest']['sha256'] and
        S.digest(values['runtime'])['sha256']==state['runtime_sha256'],
        'Current source state or original runtime identity differs')
    records=[];selected=closure.get('selected_runtime_provider_packs',[])
    S.check(selected==sorted(set(selected)) and all(0<=i<len(paths) for i in selected),'Invalid original provider selection order')
    for i,(path,row) in enumerate(zip(paths,state['providers_verified'])):
        manifest=S.read(path)
        S.check(manifest['base']==identity,'Existing source provider belongs to another base')
        records.append(dict(family=manifest['family'],manifest=S.artifact(path),verification=row['verification'],
            metadata={k:v for k,v in manifest.items() if k.endswith('_metadata') and isinstance(v,dict) and 'digest' in v},
            selected=i in selected))
    S.check(closure['runtime_provider_packs']==[dict(manifest=r['manifest'],verification=r['verification']) for r in records],
        'Original full source provider manifests/order differ from the current state')
    global_identity=diagnostic['global_provider_identity'];runtime=values['runtime']
    S.check(Path(global_identity['runtime_dll']).resolve()==runtime and global_identity['runtime_sha256']==state['runtime_sha256'],
        'Original source selection used another runtime DLL')
    objects=[S.checked(r['object']) for r in proof['verified_assembly_objects']['units']]+[Path(p) for p in closure['objects']]
    families=sorted(records[i]['family'] for i in selected)
    libraries=L.diagnostic_libraries(runtime,winsock='normal-native-libraries-v1' in families)[0]
    link=L.verify(selection/'link.rsp',profile='diagnostic',output=selection/'diagnostic-image.dll',
        objects=objects,library_choices=[libraries],exports=closure['exports'])
    return state,identity,closure,proof,records,families,objects,libraries,link


def prepare(state_file,selection,output):
    state_file,selection,output=Path(state_file).resolve(),Path(selection).resolve(),Path(output).resolve()
    S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh isolated source-envelope output required')
    state,identity,closure,stored,providers,families,objects,libraries,link=context(state_file,selection)
    inputs={}
    def seal(path):
        record=S.artifact(path);previous=inputs.setdefault(record['path'],record)
        S.check(previous==record,'Original source input changed during envelope construction');return record
    for path in [state_file,Path(state['providers']),*(ROOT/p for p in S.TOOL_FILES),
                 *(ROOT/'scripts'/p for p in F.COMMON_SOURCES),Path(__file__),Path(sys.executable),
                 selection/'closure.json',selection/'diagnostic.json',selection/'selection-verification.json',
                 selection/'initialization-closure.asm',selection/'diagnostic-stops.asm',selection/'assembly-provenance.json',
                 selection/'link.rsp',selection/'diagnostic-image.dll',*objects,*libraries,
                 Path(state['frame_manifest']),Path(state['frame_manifest']).with_name('verification.json'),
                 runtime_file(state),runtime_file(state).with_name('runtime.json')]:
        seal(path)
    for key in ('batch_summary','base_verification','source_plan','source_classes','source_methods'):seal(identity[key]['path'])
    for unit in stored['verified_assembly_objects']['units']:seal(unit['assembly']['path'])
    receipt=S.read(selection/'assembly-provenance.json')
    for unit in receipt['units']:
        if 'parallel_receipt' in unit:seal(unit['parallel_receipt']['path'])
    frame=S.read(Path(state['frame_manifest']))
    for key in ('assembly','object'):
        if key in frame:seal(frame[key]['path'])
    assembler=Path(stored['verified_assembly_objects']['assembler']['path']);seal(assembler);seal(assembler.with_name('link.exe'))
    for provider in providers:
        manifest=S.read(S.checked(provider['manifest']))
        for record in [provider['manifest'],provider['verification'],manifest['assembly'],manifest['object'],*provider['metadata'].values()]:
            seal(record['path'])
    # This is a real current full verifier invocation, not a copied success flag.
    with ReadInputs(seal) as reads:
        V=module('verify-diagnostic-closure');actual=V.verify(selection)
    S.check(actual==stored,'Current independent source/ASM/COFF verification differs from the original proof')
    after=context(state_file,selection)
    S.check((after[1],after[4],after[5],after[6],after[7],after[8])==
        (identity,providers,families,objects,libraries,link),'Original source context changed during full verification')
    for record in inputs.values():checked(record)
    output.mkdir(parents=True);proof_file=output/'source-reverification.json';S.write(proof_file,actual)
    result=dict(schema=1,scope=SCOPE,input_state=S.artifact(state_file),provider_list=S.artifact(Path(state['providers'])),
        base=identity,source_selection_directory=str(selection),source_manifest=S.artifact(selection/'closure.json'),
        source_selection=S.artifact(selection/'selection-verification.json'),current_reverification=S.artifact(proof_file),
        image=S.artifact(selection/'diagnostic-image.dll'),runtime=S.artifact(runtime_file(state)),
        providers=providers,selected_provider_families=families,link_inputs=[S.artifact(p) for p in objects+libraries],
        link_response=S.artifact(selection/'link.rsp'),link_proof=link,inputs=list(inputs.values()),tool=S.artifact(Path(__file__)),
        tool_sources=S.tools_identity(),provider_inputs=state['provider_count'],source_reverification_executed=True,
        actual_verifier_read_set_captured=True,actual_verifier_read_files=len(reads.seen),sealed_input_files=len(inputs),
        source_selection_changed=False,original_Java_Code_changed=False,original_COFF_changed=False,
        additional_candidate_in_original_full_verification=False,runtime_acceptance_claimed=False,executed_guest=False,game_started=False)
    path=output/'source-envelope.json';S.write(path,result);verify(path);return path


def verify(path):
    """Validate this exact immutable current-source chain; do not relabel an overlay."""
    path=Path(path).resolve();value=S.read(path)
    S.check(path.is_relative_to(S.ART) and value['schema']==1 and value['scope']==SCOPE and
        value['tool']==S.artifact(Path(__file__)) and value['tool'] in value['inputs'] and
        value['tool_sources']==S.tools_identity() and value['source_reverification_executed'] is True and
        value['actual_verifier_read_set_captured'] is True and
        not any(value[k] for k in ('source_selection_changed','original_Java_Code_changed','original_COFF_changed',
            'additional_candidate_in_original_full_verification','runtime_acceptance_claimed','executed_guest','game_started')),
        'Source-envelope provenance/scope changed')
    for record in value['inputs']:checked(record)
    state,identity,closure,proof,providers,families,objects,libraries,link=context(checked(value['input_state']),
        Path(value['source_selection_directory']))
    selection=Path(value['source_selection_directory'])
    S.check(value['base']==identity and value['providers']==providers and value['selected_provider_families']==families and
        value['provider_inputs']==state['provider_count'] and checked(value['provider_list'])==Path(state['providers']) and
        value['link_inputs']==[S.artifact(p) for p in objects+libraries] and value['link_proof']==link and
        checked(value['link_response'])==selection/'link.rsp' and checked(value['source_manifest'])==selection/'closure.json' and
        checked(value['source_selection'])==selection/'selection-verification.json' and
        checked(value['image'])==selection/'diagnostic-image.dll' and
        checked(value['runtime'])==runtime_file(state) and
        S.read(checked(value['current_reverification']))==proof,
        'Envelope no longer describes its exact current original source/object chain')
    for record in value['inputs']:checked(record)
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path);parser.add_argument('--selection',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--verify',type=Path);args=parser.parse_args()
    if args.verify:verify(args.verify);print(args.verify)
    else:print(prepare(args.state,args.selection,args.output))
