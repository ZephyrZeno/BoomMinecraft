"""Bind constructor probe sites to an accepted, immutable framed source image.

The accepted manifest SHA is mandatory. All captured link/tool/source inputs
are rehashed; original JDK image classes and original input archives are also
checked. This reuses the already performed source proof, not a verified flag
from an arbitrary new manifest.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile


def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


A=module('constructor_site_adapter_source','native-frame-adapters.py');S=A.S
R=module('constructor_site_original_methods','verify-batch-frames.py')
C=module('constructor_site_descriptors','constructor-provider-source.py')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--framed',type=Path,required=True);p.add_argument('--accepted-sha256',required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    framed_path=a.framed.resolve();output=a.output.resolve()
    S.check(framed_path.is_relative_to(S.ART) and output.is_relative_to(S.ART),'Constructor source probe must stay in project .boom')
    S.check(S.digest(framed_path)['sha256']==a.accepted_sha256,'Accepted framed source manifest changed')
    framed=S.read(framed_path)
    S.check(framed['linked'] and framed['diagnostic_only'] and framed['baseline_revalidated']['verified'] and framed['adapters_revalidated']['verified'],
            'Constructor source probe needs an accepted source-revalidated framed build')
    for record in [*framed['link_inputs'].values(),*framed['source_receipts'].values(),framed['image'],framed['relinker'],framed['linker'],framed['source_configuration']]:
        S.check(S.artifact(record['path'])==record,'Accepted framed build dependency changed: '+record['path'])
    adapters=S.read(S.checked(framed['adapters']))
    S.check(adapters['tool_sources']==A.tools(),'Accepted framed adapter source tools changed')
    baseline=Path(framed['baseline']);closure=S.read(baseline/'closure.json')
    identity,summary,classes=S.base(closure['batch'],closure['plan'])
    S.check(identity==adapters['base'],'Constructor source image input/plan identity changed')
    names={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    source_image=(Path(summary['frames']['original_system_catalog']['path']).parent/'image').resolve()
    original_checked=0
    for c in classes:
        if not c['origin']['source_id'].startswith('jdk:'):continue
        source=(source_image/c['origin']['jar_entry']).resolve()
        S.check(source.is_relative_to(source_image),'Constructor source class escaped original image')
        S.check(hashlib.sha256(source.read_bytes()).hexdigest()==c['origin']['sha256'],'Original constructor image class changed')
        original_checked+=1
    for record in summary['frames']['original_input_files'].values():
        actual=S.digest(record['path'])
        S.check(all(record['digest'][k]==v for k,v in actual.items()),'Original constructor input archive changed')
    specs=[('java/lang/Object','()V')]+list(zip(('java/lang/Boolean','java/lang/Byte','java/lang/Character',
        'java/lang/Short','java/lang/Integer','java/lang/Long','java/lang/Float','java/lang/Double'),('(Z)V','(B)V','(C)V','(S)V','(I)V','(J)V','(F)V','(D)V')))
    specs += [('java/util/AbstractMap$SimpleImmutableEntry','(Ljava/lang/Object;Ljava/lang/Object;)V'),
              ('java/lang/String','([C)V'),('java/lang/StringBuilder','(Ljava/lang/String;)V'),('java/util/ArrayList','(Ljava/util/Collection;)V')]
    wanted=set(specs);methods={}
    with zipfile.ZipFile(S.checked(summary['frames']['index'])) as z:
        for line in z.open('methods.jsonl'):
            m=json.loads(line);key=(m['class_name'],m['descriptor'])
            if m['name']=='<init>' and key in wanted and str(m['id']) in closure['selected_methods']:methods[key]=m
    S.check(set(methods)==wanted,'Original source constructor body is not selected in accepted image')
    ids={names['bootstrap',name] for name,_ in specs};layouts={}
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['class_id'] in ids:layouts[row['class_id']]=row['candidate']
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as z:
        types=[json.loads(l) for l in z.open('types.jsonl')]
    byname={(t['defining_loader'],t['name']):t['id'] for t in types}
    symbols={'boom_constructor_callsite'};sites=[];parts=['option casemap:none\n']
    body=['.const\nALIGN 8\nPUBLIC boom_constructor_probe_sites\nboom_constructor_probe_sites LABEL QWORD\n']
    body.extend(f' QWORD OFFSET constructor_probe_site{i}\n' for i in range(len(specs)))
    original=C.RawClasses(summary)
    try:
        for index,(name,descriptor) in enumerate(specs):
            m=methods[name,descriptor];owner=m['class_id'];c=classes[owner]
            actual,raw=R.original_methods(original.read(c));slot=c['method_ids'].index(m['id']);method=raw[slot]
            S.check(actual==name and method['name']=='<init>' and method['descriptor']==descriptor and method['code'] is not None and
                    hashlib.sha256(method['code'][0]).hexdigest()==m['code_sha256'], 'Original constructor Code differs')
            selected=closure['selected_methods'][str(m['id'])]
            S.check(selected['code_sha256']==m['code_sha256'] and selected['source_sha256']==c['origin']['sha256'], 'Selected constructor source identity differs')
            params=C.parameter_names(descriptor);param_rows=[]
            for d in params:
                if d in 'ZBCSIJFD':kind='ZBCSIJFD'.index(d);type_name=d;ptr='0'
                else:kind=8;type_name=d[1:-1] if d.startswith('L') else d;ptr='OFFSET boom_t'+str(byname['bootstrap',type_name]);symbols.add(ptr.split()[-1])
                param_rows.append((kind,byname['bootstrap',type_name],ptr))
            layout=layouts[owner];S.check(layout is not None,'Original source constructor layout missing')
            def field(n):
                found=[f for f in layout['fields'] if f['member']['owner']==owner and f['member']['name']==n]
                S.check(len(found)==1,'Constructor output field missing: '+n);return dict(offset=found[0]['offset'],width=found[0]['storage_bytes'])
            site=dict(index=index,name=name,class_id=owner,method_id=m['id'],descriptor=descriptor,nargs=len(params),
                parameter_kinds=[r[0] for r in param_rows],payload_bytes=layout['payload_bytes'],reference_prefix=layout['reference_prefix'])
            if name.startswith('java/lang/') and name not in ('java/lang/Object','java/lang/String','java/lang/StringBuilder'):site['value']=field('value')
            if name=='java/util/AbstractMap$SimpleImmutableEntry':site['key']=field('key');site['value']=field('value')
            sites.append(site)
            for symbol in (f'boom_layout{owner}',f'boom_class{owner}',f"boom_m{m['id']}"):symbols.add(symbol)
            body.append(f"ALIGN 8\nconstructor_probe_site{index} DWORD 0564E4943h,1,{owner},{len(params)},0,0\n QWORD OFFSET boom_layout{owner},OFFSET boom_class{owner},OFFSET boom_m{m['id']},{'OFFSET constructor_probe_params'+str(index) if params else '0'}\n DWORD {m['id']},0\n")
            if params:
                body.append(f'constructor_probe_params{index} LABEL BYTE\n')
                body.extend(f' DWORD {kind},{type_id}\n QWORD {ptr}\n' for kind,type_id,ptr in param_rows)
    finally:original.close()
    parts.extend(f"EXTERN {symbol}:{'PROC' if symbol=='boom_constructor_callsite' or symbol.startswith('boom_m') else 'BYTE'}\n" for symbol in sorted(symbols))
    parts.extend(body)
    parts.append('.code\nPUBLIC boom_constructor_probe_call\nboom_constructor_probe_call PROC FRAME\n sub rsp,56\n .allocstack 56\n .endprolog\n mov r10,QWORD PTR [rsp+96]\n mov QWORD PTR [rsp+32],r10\n call boom_constructor_callsite\n mov r10,QWORD PTR [rsp+32]\n mov DWORD PTR [r10],edx\n add rsp,56\n ret\nboom_constructor_probe_call ENDP\nEND\n')
    output.mkdir(parents=True,exist_ok=True)
    (output/'sites.asm').write_text(''.join(parts),encoding='utf-8')
    configuration=S.read(framed_path.parent/'source.json');configuration.update(cases=sites,
        object_array_type=byname['bootstrap','[Ljava/lang/Object;'],primitive_byte_array_type=byname['bootstrap','[B'],
        class_flag_cases_omitted=True,accepted_framed_manifest=S.artifact(framed_path),original_system_classes_rehashed=original_checked,
        source_native_binding_provided=False,game_started=False)
    S.write(output/'source.json',configuration)
    objects=[str(baseline/'initialization-closure.obj'),str(baseline/'diagnostic-stops.obj')]+[framed['replacement_objects'].get(p,p) for p in closure['objects']]
    S.write(output/'link-source.json',dict(objects=objects,exports=closure['exports'],runtime=closure['runtime'] if 'runtime' in closure else None,
        accepted_framed_manifest=S.artifact(framed_path),Java_ASM_or_COFF_modified=False))
    print(json.dumps(dict(sites=len(sites),original_system_classes_rehashed=original_checked,source_native_binding_provided=False,game_started=False)))
