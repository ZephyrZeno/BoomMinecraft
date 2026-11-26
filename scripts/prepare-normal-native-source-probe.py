"""Capture an accepted source image for scoped registration or real Java throws."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('normal_native_source_probe_io',ROOT/'scripts/runtime-provider-source.py')
S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)


def prepare(directory,accepted,output,mode):
    directory,output=Path(directory).resolve(),Path(output).resolve()
    S.check(directory.is_relative_to(S.ART) and output.is_relative_to(S.ART) and not output.exists(),'Use a fresh isolated source probe output')
    proof_path=directory/'selection-verification.json';proof=S.read(proof_path);closure=S.read(directory/'closure.json')
    S.check(S.digest(proof_path)['sha256']==accepted and proof['verified'] and proof['diagnostic_only'] and not proof['source_closure_complete'],
            'Explicitly accepted normal source proof differs')
    S.check(hashlib.sha256((directory/'initialization-closure.asm').read_text(encoding='utf-8').encode()).hexdigest()==proof['closure_assembly_sha256'],
            'Accepted normal Java assembly changed')
    family={'scoped-memory':'normal-scoped-memory-registration-v1','throwable':'normal-throwable-v1'}[mode]
    records=closure['runtime_provider_packs'];packs=[S.read(S.checked(p['manifest'])) for p in records]
    matches=[m for m in packs if m['family']==family];S.check(len(matches)==1,'Required normal source family is missing')
    m=matches[0];S.check(m['tool_sources']==S.tools_identity(),'Normal source provider tool identity changed')
    S.check(m['object']['path'] in closure['objects'] and str(m['methods'][0]['method']) in closure['selected_runtime_provider_natives'],
            'Normal source native is not selected in the accepted image')
    key={'scoped-memory':'scoped_memory_metadata','throwable':'normal_throwable_metadata'}[mode]
    meta_path=S.checked(m[key]);meta=S.read(meta_path)
    class_path=S.checked(m['base']['source_classes']);classes=[json.loads(l) for l in class_path.read_text(encoding='utf-8').splitlines()]
    names={(c['origin']['loader'],c['name']):c for c in classes}
    def method(owner,name,desc):
        c=names['bootstrap',owner]
        found=[(i,r) for i,r in closure['selected_methods'].items() if r['class_id']==c['id'] and (r['name'],r['descriptor'])==(name,desc)]
        S.check(c['origin']['source_id']=='jdk:java.base' and len(found)==1 and found[0][1]['source_sha256']==c['origin']['sha256'],
                'Required original Java probe method is not selected: '+owner+'.'+name)
        return int(found[0][0])
    def static(c,name,desc,access=0x1a):
        found=[i for i,f in enumerate(c['fields']) if (f['name'],f['descriptor'],f['access'])==(name,desc,access)]
        S.check(len(found)==1,'Original static sentinel/instance declaration differs: '+name)
        return f"boom_s{c['id']}_{found[0]}"
    def selected_symbol(id_):
        candidates=[f'boom_m{id_}',f'boom_m{id_}_body']
        found=[n for n in candidates if n in closure['selected_function_sha256'] and n in closure['exports']]
        S.check(found,'Required original Java function is not exported in the accepted image')
        return found[0]
    native=m['methods'][0];extra=dict(native_symbol=f"boom_m{native['method']}",owner_class=native['class_id'],pool=m['pool_symbol'],service=m['service_symbol'])
    more=[]
    if mode=='scoped-memory':
        c=m['owner_source'];getter=method(c['name'],'getScopedMemoryAccess','()Ljdk/internal/misc/ScopedMemoryAccess;')
        buffer=names['bootstrap','java/nio/Buffer'];method('java/nio/Buffer','<clinit>','()V')
        extra.update(getter_source_method_id=getter,getter_via_original_Buffer_initializer=True,buffer_class=buffer['id'],
            buffer_scoped_access=static(buffer,'SCOPED_MEMORY_ACCESS','Ljdk/internal/misc/ScopedMemoryAccess;',0x18),singleton=static(c,'theScopedMemoryAccess','Ljdk/internal/misc/ScopedMemoryAccess;'),
            unsafe=static(c,'UNSAFE','Ljdk/internal/misc/Unsafe;'),unsafe_class=names['bootstrap','jdk/internal/misc/Unsafe']['id'])
    else:
        error_class=names['bootstrap','java/lang/IllegalAccessError'];root=classes[meta['root']]
        row=next(r for r in meta['rows'] if r['class_id']==error_class['id'])
        caller=method('jdk/internal/misc/Unsafe','throwIllegalAccessError','()V')
        summary=S.read(Path(closure['batch'])/'summary.json');layouts=S.checked(summary['layouts']);more.append(layouts)
        layout=next(json.loads(l) for l in layouts.read_text(encoding='utf-8').splitlines() if json.loads(l)['class_id']==error_class['id'])
        S.check(layout['candidate'] is not None and layout['diagnostic'] is None,'Original IllegalAccessError layout unavailable')
        fields={}
        for name,desc in [('cause','Ljava/lang/Throwable;'),('detailMessage','Ljava/lang/String;'),('suppressedExceptions','Ljava/util/List;')]:
            declared=[(i,f) for i,f in enumerate(root['fields']) if (f['name'],f['descriptor'],f['access'])==(name,desc,2)]
            S.check(len(declared)==1,'Original Throwable constructor field differs')
            member=dict(owner=root['id'],index=declared[0][0],name=name,descriptor=desc,access=2)
            stored=[f for f in layout['candidate']['fields'] if f['member']==member]
            S.check(len(stored)==1 and stored[0]['reference'] and stored[0]['storage_bytes']==8,'Original inherited Throwable field shape differs')
            fields[name]=stored[0]['offset']
        extra.update(caller=selected_symbol(caller),caller_id=caller,exception_class=error_class['id'],exception_fields=row,constructor_fields=fields,
            unassigned_stack=static(root,'UNASSIGNED_STACK','[Ljava/lang/StackTraceElement;'),suppressed_sentinel=static(root,'SUPPRESSED_SENTINEL','Ljava/util/List;'))
    runtime=Path(S.read(directory/'diagnostic.json')['global_provider_identity']['runtime_dll'])
    paths=[directory/p for p in ('closure.json','selection-verification.json','initialization-closure.asm','initialization-closure.obj','diagnostic-stops.obj','diagnostic-image.dll')]
    paths.extend(Path(p) for p in closure['objects']);paths.extend((runtime,meta_path,class_path,ROOT/'tests/host/NormalNativeSourceProbe.cs',Path(__file__),ROOT/'scripts/Test-NormalNativeSource.ps1'));paths.extend(more)
    for p in records:paths.extend((S.checked(p['manifest']),S.checked(p['verification'])))
    result=dict(schema=1,mode=mode,image=str(directory/'diagnostic-image.dll'),runtime=str(runtime),metadata=meta,
        roots=[r['class_id'] for r in closure['requested_class_roots']],inputs=[S.artifact(p) for p in dict.fromkeys(paths)],
        full_VM_bootstrap=False,game_started=False,**extra)
    S.write(output,result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);p.add_argument('--accepted-verification-sha256',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--mode',choices=['scoped-memory','throwable'],required=True)
    a=p.parse_args();prepare(a.directory,a.accepted_verification_sha256,a.output,a.mode);print(json.dumps(dict(source=str(a.output),game_started=False)))
