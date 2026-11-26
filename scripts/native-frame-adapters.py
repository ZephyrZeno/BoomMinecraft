"""Add genuine ASM native entry frames to verified provider objects.

Original provider services and metadata stay byte-for-byte in generated ASM;
only their entry adapters change. The replacement object and one frame-data
overlay must later be selected together by a source-verifying linker.
"""
import argparse
import json
from pathlib import Path
import subprocess
import importlib.util


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


V=module('framed_adapter_original_providers','verify-runtime-provider-pack.py');S=V.S
F=module('framed_adapter_original_rows','native-frame-overlay.py')
R=module('framed_adapter_entry_model','verify-batch-frames.py')


def tools():
    return {**S.tools_identity(),**F.tools(),
            'scripts/native-frame-adapters.py':S.digest(Path(__file__))['sha256']}


def rewrite(text,manifest,natives):
    imports={'boom_trace_enter','boom_trace_leave','boom_trace_pool'};ids=[]
    for m in manifest['methods']:
        i=m['method'];row=natives.get(i)
        S.check(row is not None and row['flags']&32 and not row['flags']&128,
                'Provider entry has no available original native frame')
        S.check(all(row[k]==m[k] for k in ('class_id','class_sha256','loader','source_id','name','descriptor','access'))
                and row['class_name']==m['owner'],'Provider entry native frame declaration differs')
        old=V.wrapper(m,manifest['pool_symbol'],manifest['service_symbol'])
        S.check(text.count(old)==1,'Provider frame adapter requires one exact original wrapper')
        framed=(f'.code\nPUBLIC boom_m{i}\nPUBLIC boom_m{i}_native\n'+
                R.native_adapter(i,m['class_id'],manifest['pool_symbol'],manifest['service_symbol'],m['operation'])[len('.code\n'):])
        text=text.replace(old,framed,1);imports.add(f'boom_trace_method{i}');ids.append(i)
    S.check(text.startswith('option casemap:none\n'),'Provider frame adapter ASM prefix differs')
    prefix=''.join(f"EXTERN {s}:{'PROC' if s in {'boom_trace_enter','boom_trace_leave'} else 'BYTE'}\n"
                   for s in sorted(imports) if not any(line.startswith('EXTERN '+s+':') for line in text.splitlines()))
    text='option casemap:none\n'+prefix+text[len('option casemap:none\n'):]
    return text,imports,ids


def source(batch,plan,provider_paths,overlay_path):
    overlay_path=Path(overlay_path).resolve();overlay= S.read(overlay_path)
    proof=F.verify(overlay_path,batch,plan)
    S.check(S.read(overlay_path.with_name('verification.json'))==proof,'Native frame overlay verification receipt differs')
    packs=V.load_packs(batch,plan,provider_paths)
    S.check(packs,'Native frame adapters require verified provider services')
    rows={n['id']:n for n in overlay['source']['original_native_declarations']};units=[]
    for index,p in enumerate(packs):
        m=p['manifest'];S.check(m['base']==overlay['source']['base'],'Provider and frame overlay source identity differs')
        text=S.checked(m['assembly']).read_text(encoding='utf-8')
        adapted,imports,ids=rewrite(text,m,rows)
        units.append(dict(index=index,family=m['family'],provider=p['reference'],replaced_object=m['object'],
            native_methods=ids,expected_exports=m['exports'],expected_imports=sorted(set(m['imports'])|imports),text=adapted))
    frame_ref=dict(manifest=S.artifact(overlay_path),verification=S.artifact(overlay_path.with_name('verification.json')))
    return units,V.references(packs),frame_ref,overlay['source']['base']


def verify(path,batch,plan):
    path=Path(path).resolve();S.check(path.is_relative_to(S.ART),'Frame adapters must remain in project .boom')
    m=S.read(path);provider_paths=[str(S.checked(p['manifest'])) for p in m['source_provider_packs']]
    frame_path=S.checked(m['frame_overlay']['manifest'])
    expected,refs,frame_ref,base=source(batch,plan,provider_paths,frame_path)
    S.check(m['schema']==1 and m['source_provider_packs']==refs and m['frame_overlay']==frame_ref and m['base']==base,
            'Native frame adapter provenance changed')
    S.check(m['tool_sources']==tools() and S.artifact(m['assembler']['path'])==m['assembler'],
            'Native frame adapter tools changed')
    S.check(m['native_implementations_added']==0 and m['base_Java_ASM_and_COFF_modified'] is False,
            'Native entry adaptation cannot add native services or replace Java Code')
    for key in ('linked','executed','all_native_frames','stack_roots','automatic_gc','game_started'):
        S.check(m[key] is False,'Native entry adaptation overclaims execution: '+key)
    S.check(len(m['units'])==len(expected),'Native frame adapter unit count differs')
    coff=S.module('framed_provider_actual_coff','verify-batch-assembly.py');methods=[]
    for actual,want in zip(m['units'],expected):
        S.check(all(actual[k]==want[k] for k in ('index','family','provider','replaced_object','native_methods','expected_exports','expected_imports')),
                'Native frame adapter unit source contract differs')
        asm=S.checked(actual['assembly']);obj=S.checked(actual['object'])
        S.check(asm.parent==path.parent and obj.parent==path.parent and asm.read_text(encoding='utf-8')==want['text'],
                'Native frame adapter changed source metadata or service bodies')
        defined,undefined=coff.coff_symbols(obj)
        S.check(defined==set(want['expected_exports']) and undefined==set(want['expected_imports']),
                'Native frame adapter COFF imports/definitions differ')
        methods+=want['native_methods']
    S.check(len(methods)==len(set(methods)),'Native frame adapters overlap source declarations')
    return dict(verified=True,scope='original_provider_entry_frame_replacements_and_actual_COFF_only',
        manifest=str(path),manifest_sha256=S.digest(path)['sha256'],verifier_sha256=S.digest(Path(__file__))['sha256'],
        units=len(expected),framed_entry_methods=len(methods),native_implementations_added=0,
        base_Java_ASM_and_COFF_modified=False,linked=False,executed=False,all_native_frames=False,game_started=False)


def build(batch,plan,providers,overlay,output,assembler):
    output=Path(output).resolve();assembler=Path(assembler).resolve()
    S.check(output.is_relative_to(S.ART) and not output.exists(),'Frame adapters need a fresh isolated .boom directory')
    expected,refs,frame_ref,base=source(batch,plan,providers,overlay)
    tool_identity=tools();assembler_identity=S.artifact(assembler);output.mkdir(parents=True);units=[]
    for expected_unit in expected:
        unit=dict(expected_unit);text=unit.pop('text');stem=f"{unit['index']:04}"
        asm=output/(stem+'.asm');obj=output/(stem+'.obj');asm.write_text(text,encoding='utf-8')
        with (output/(stem+'-assembler.log')).open('wb') as log:
            result=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(asm)],stdout=log,stderr=subprocess.STDOUT)
        S.check(result.returncode==0,'Native frame adapter assembly failed; inspect '+stem+'-assembler.log')
        unit.update(assembly=S.artifact(asm),object=S.artifact(obj));units.append(unit)
    S.check(tools()==tool_identity and S.artifact(assembler)==assembler_identity,'Native frame adapter tools changed during assembly')
    manifest=dict(schema=1,base=base,source_provider_packs=refs,frame_overlay=frame_ref,tool_sources=tool_identity,
        assembler=assembler_identity,units=units,native_implementations_added=0,base_Java_ASM_and_COFF_modified=False,
        linked=False,executed=False,all_native_frames=False,stack_roots=False,automatic_gc=False,game_started=False)
    S.write(output/'adapters.json',manifest);return output/'adapters.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch',type=Path,required=True);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--provider',type=Path,action='append',default=[]);p.add_argument('--frame-overlay',type=Path)
    p.add_argument('--output',type=Path);p.add_argument('--assembler',type=Path);p.add_argument('--verify',type=Path)
    a=p.parse_args()
    if a.verify:
        result=verify(a.verify,a.batch,a.plan);S.write(a.verify.with_name('verification.json'),result);print(json.dumps(result))
    else:
        if not a.output or not a.assembler or not a.frame_overlay or not a.provider:p.error('Build requires providers, frame overlay, output and assembler')
        print(build(a.batch,a.plan,a.provider,a.frame_overlay,a.output,a.assembler))
