"""Revalidate and relink a diagnostic image with framed provider entries only.

No ordinary Java source/COFF is rewritten. Both the old source closure and the
replacement adapters are independently revalidated before the owned link; all
input hashes are checked again after it. This remains a development image.
"""
import argparse
import json
from pathlib import Path
import subprocess
import importlib.util


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


A=module('relink_framed_adapters','native-frame-adapters.py');S=A.S


def build(baseline,adapters,runtime,output,linker,synchronization):
    baseline=Path(baseline).resolve();output=Path(output).resolve();runtime=Path(runtime).resolve()
    S.check(baseline.is_relative_to(S.ART) and output.is_relative_to(S.ART) and not output.exists(),
            'Framed diagnostic relinking needs project artifacts and a fresh output')
    original=S.read(baseline/'closure.json');batch=Path(original['batch']);plan=Path(original['plan'])
    S.check(original.get('explicit_raw_slot_class_flags_fixture') and original.get('diagnostic_only'),
            'This executable probe requires the original class-flags diagnostic fixture')
    own_identity=S.artifact(Path(__file__))
    baseline_verifier=module('relink_fresh_baseline_verifier','verify-diagnostic-closure.py')
    baseline_proof=baseline_verifier.verify(baseline)
    S.check(baseline_proof==S.read(baseline/'selection-verification.json'),
            'Framed diagnostic baseline source proof changed')
    adapters=Path(adapters).resolve();proof=A.verify(adapters,batch,plan)
    S.check(proof==S.read(adapters.with_name('verification.json')),'Framed native adapters proof changed')
    adapted=S.read(adapters)
    S.check(original['runtime_provider_packs']==adapted['source_provider_packs'],
            'Framed diagnostic provider source set differs')
    overlay_path=S.checked(adapted['frame_overlay']['manifest']);overlay=S.read(overlay_path)
    metadata=S.read(runtime/'runtime.json');dll=runtime/'boom-runtime.dll'
    S.check(S.digest(dll)['sha256']==metadata['sha256'] and
            all(metadata['sources'].get(p)==h for p,h in overlay['source']['runtime_kernel_sha256'].items()),
            'Framed diagnostic runtime source/ABI differs')
    replacements={u['replaced_object']['path']:u['object']['path'] for u in adapted['units']}
    replacements[overlay['source']['replaced_data_object']['path']]=overlay['object']['path']
    old_objects=original['objects'];S.check(len(old_objects)==len(set(old_objects)), 'Baseline object list has duplicates')
    S.check(overlay['source']['replaced_data_object']['path'] in old_objects,'Baseline omitted original frame data object')
    selected_replacements={p:replacements[p] for p in old_objects if p in replacements}
    S.check(len(selected_replacements)>1,'No original provider entry was selected for framing')
    objects=[str(baseline/'initialization-closure.obj'),str(baseline/'diagnostic-stops.obj')]+[replacements.get(p,p) for p in old_objects]
    S.check(len(objects)==len(set(objects)),'Framed object replacement produced duplicates')
    for old in selected_replacements:S.check(old not in objects,'Old and framed objects cannot both be linked')
    link_inputs={p:S.artifact(p) for p in set(old_objects+objects+[str(runtime/'boom-runtime.lib'),str(synchronization),str(linker),str(dll)])}
    receipt_paths=[str(baseline/'closure.json'),str(baseline/'selection-verification.json'),str(baseline/'source.json'),
        str(runtime/'runtime.json'),str(plan/'classes.jsonl'),str(adapters),str(overlay_path)]
    receipt_paths += [str(Path(__file__).with_name(n)) for n in ('verify-diagnostic-closure.py',
        'verify-initialization-closure.py','provider-verification-reuse.py')]
    receipts={p:S.artifact(p) for p in receipt_paths}
    output.mkdir(parents=True);target=output/'framed-image.dll'
    lines=['/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT','/BREPRO',f'/OUT:"{target}"']
    lines+=['"'+p+'"' for p in objects+[str(runtime/'boom-runtime.lib'),str(synchronization)]]
    lines+=['/EXPORT:'+s for s in sorted(set(original['exports']))]
    rsp=output/'link.rsp';rsp.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    with (output/'link.log').open('wb') as log:
        result=subprocess.run([str(linker),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT)
    S.check(result.returncode==0,'Framed diagnostic link failed; inspect link.log')
    for p,record in {**link_inputs,**receipts}.items():S.check(S.artifact(p)==record,'Framed diagnostic input changed during link: '+p)
    S.check(S.artifact(Path(__file__))==own_identity,'Framed diagnostic relinker changed during build')
    exports=module('relink_actual_pe_exports','diagnostic-closure.py').pe_exports(target)
    S.check(exports==set(original['exports']),'Framed diagnostic DLL exports differ from original source closure')
    classes=[json.loads(l) for l in (plan/'classes.jsonl').open(encoding='utf-8')]
    names={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    configuration=S.read(baseline/'source.json')
    ctor_unit=next(u for u in adapted['units'] if u['family']=='normal-constructors-v1')
    ctor_provider=S.read(S.checked(ctor_unit['provider']))
    ctor_metadata=S.read(S.checked(ctor_provider['constructor_metadata']))
    configuration.update(native_constructor_symbol='boom_m'+str(ctor_provider['methods'][0]['method']),
        deferred_method_class=names['bootstrap','java/lang/reflect/Method'],
        cold_accessible_class=names['bootstrap','java/lang/reflect/AccessibleObject'],
        cold_constructor_class=ctor_metadata['constructor_class'],constructor_clazz_offset=ctor_metadata['field_offsets'][0])
    S.write(output/'source.json',configuration)
    manifest=dict(schema=1,diagnostic_only=True,baseline=str(baseline),baseline_revalidated=baseline_proof,
        adapters=S.artifact(adapters),adapters_revalidated=proof,frame_overlay=S.artifact(overlay_path),
        replacement_objects=selected_replacements,link_inputs=link_inputs,source_receipts=receipts,
        image=S.artifact(target),relinker=own_identity,linker=S.artifact(linker),source_configuration=S.artifact(output/'source.json'),
        Java_codegen_rerun=False,Java_ASM_or_COFF_modified=False,Java_reassembled_in_this_relink=False,
        native_implementations_added=0,linked=True,executed=False,source_closure_complete=False,game_started=False)
    S.write(output/'framed.json',manifest)
    print(json.dumps(dict(linked=True,diagnostic_only=True,provider_objects_replaced=len(selected_replacements)-1,
        framed_entries=proof['framed_entry_methods'],output=str(output),executed=False,game_started=False)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('baseline','adapters','runtime','output','linker','synchronization'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.baseline,a.adapters,a.runtime,a.output,a.linker,a.synchronization)
