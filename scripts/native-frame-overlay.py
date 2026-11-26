"""Extend the frozen ABI3 frame table with original native declarations only.

This offline data overlay replaces the base frame-data object at link time. It
does not implement a native method or claim its wrapper already records a frame.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile


def module(name, file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


S=module('native_overlay_identity','runtime-provider-source.py')
R=module('native_overlay_original_frames','verify-batch-frames.py')
C=module('native_overlay_original_classes','constructor-provider-source.py')
TOOLS=('scripts/native-frame-overlay.py','scripts/runtime-provider-source.py',
       'scripts/constructor-provider-source.py','scripts/system-class-inputs.py','scripts/verify-batch-frames.py',
       'scripts/verify-batch-assembly.py','scripts/verify-batch-metadata.py','scripts/provider-tool-manifest.py')


def tools():return {p:S.digest(S.ROOT/p)['sha256'] for p in TOOLS}


def merge(base, natives, limit=1048576):
    """Rows are (original method ID, flags, original class ID, Code bytes)."""
    S.check(base and [r[0] for r in base]==sorted({r[0] for r in base}),
            'Base frame rows have duplicate or unordered source IDs')
    byid={r[0]:r for r in base};seen=set();added=[]
    for row in natives:
        i,flags,_,length=row
        S.check(i not in seen and flags&32 and flags&~255==0 and length==0,
                'Invalid or duplicate original native frame row')
        seen.add(i)
        if i in byid:S.check(byid[i]==row,'Native overlay would replace a base frame row')
        else:byid[i]=row;added.append(i)
    S.check(len(byid)<=limit,'Native frame overlay exceeds runtime ABI capacity')
    return sorted(byid.values()),sorted(added)


def body(rows):
    parts=['.const\nALIGN 8\nPUBLIC boom_trace_methods\nboom_trace_methods LABEL BYTE\n']
    for i,flags,owner,length in rows:
        declaring='0' if flags&128 else f'OFFSET boom_t{owner}'
        parts.append(f'PUBLIC boom_trace_method{i}\nboom_trace_method{i} DWORD {i},{flags}\n QWORD {declaring}\n DWORD {length},{owner}\n QWORD 0\n')
    parts.append(f'.data\nALIGN 8\nPUBLIC boom_trace_pool\nboom_trace_pool DWORD 05452504Ch,3,0,0FFFFFFFFh\n DWORD {len(rows)},0\n QWORD OFFSET boom_trace_methods,0,0\n.code\nPUBLIC boom_release_trace_pool\nboom_release_trace_pool PROC\n lea rcx,boom_trace_pool\n jmp boom_trace_release\nboom_release_trace_pool ENDP\n\n')
    return ''.join(parts)


def symbols(rows):
    exports={'boom_trace_methods','boom_trace_pool','boom_release_trace_pool'}|{f'boom_trace_method{r[0]}' for r in rows}
    imports={'boom_trace_release'}|{f'boom_t{r[2]}' for r in rows if not r[1]&128}
    return exports,imports


def assembly(rows):
    _,imports=symbols(rows)
    return 'option casemap:none\n'+''.join(f"EXTERN {n}:{'PROC' if n=='boom_trace_release' else 'BYTE'}\n" for n in sorted(imports))+'.code\n'+body(rows)+'\nEND\n'


def native_contract(source, planned, raw):
    S.check(raw['access']&0x500==0x100 and raw['code'] is None,
            'Native frame source must be an original native without Java Code')
    S.check((raw['name'],raw['descriptor'],raw['access'])==
            (planned['symbol']['name'],planned['symbol']['descriptor'],planned['access']) and
            planned['class_id']==source['id'] and planned['class_sha256']==source['origin']['sha256'] and
            planned['code_sha256'] is None,'Native frame declaration differs from source plan')


def index(batch, plan):
    identity,summary,classes=S.base(batch,plan)
    frames=summary['frames']
    S.check((frames['abi'],frames['pool_bytes'],frames['method_row_bytes'])==(3,48,32),
            'Native overlay requires the frozen ABI3 frame table')
    frame_index=S.checked(frames['index']);base_object=S.checked(frames['units'][0]['object'])
    base_assembly=S.checked(frames['units'][0]['assembly'])
    with zipfile.ZipFile(frame_index) as z:
        base=[(r['id'],r['flags'],r['class_id'],r['code_length'])
              for line in z.open('methods.jsonl') if (r:=json.loads(line))]
    S.check(len(base)==frames['methods'],'Base frame index count differs')
    text=base_assembly.read_text(encoding='utf-8')
    S.check(text.endswith('\nEND\n') and text.partition('.code\n')[2][:-5]==body(base),
            'Base frame ASM differs from its verified original rows')
    coff=S.module('native_overlay_actual_base_coff','verify-batch-assembly.py')
    S.check(coff.coff_symbols(base_object)==symbols(base),'Base frame COFF differs from source rows')
    with zipfile.ZipFile(S.checked(summary['runtime_metadata']['index'])) as z:
        available={json.loads(l)['id'] for l in z.open('types.jsonl')}
    hierarchy=S.module('native_overlay_source_hierarchy','verify-batch-metadata.py')
    lookup,_,parents,_=hierarchy.source_model(classes)
    accessor=lookup('bootstrap','jdk/internal/reflect/MethodAccessorImpl')
    wanted={}
    with (Path(plan)/'methods.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            m=json.loads(line)
            if m['access']&0x100:wanted.setdefault(m['class_id'],{})[m['id']]=m
    raw_classes=C.RawClasses(summary);natives=[];native_rows=[]
    try:
        for owner,methods in sorted(wanted.items()):
            c=classes[owner];o=c['origin'];name,raw=R.original_methods(raw_classes.read(c))
            S.check(name==c['name'] and len(raw)==len(c['method_ids']),'Native frame original inventory differs')
            trusted=o['loader'] in ('bootstrap','platform') and o['source_id'].startswith('jdk:') and not o.get('generated')
            parent=owner;seen=set();ignored=False
            while parent is not None and parent not in seen:
                seen.add(parent)
                if parent==accessor:ignored=True;break
                parent=parents.get(parent)
            found=set()
            for i,m in zip(c['method_ids'],raw):
                if not m['access']&0x100:continue
                S.check(i in methods,'Original native is missing from the source plan')
                native_contract(c,methods[i],m);found.add(i)
                flags=R.flags(name,m,trusted,bool(o.get('generated')),ignored)|(0 if owner in available else 128)
                native_rows.append((i,flags,owner,0))
                natives.append(dict(id=i,class_id=owner,class_sha256=o['sha256'],loader=o['loader'],source_id=o['source_id'],
                    class_name=name,name=m['name'],descriptor=m['descriptor'],access=m['access'],annotations=m['annotations'],flags=flags))
            S.check(found==set(methods),'Source native inventory was not reconstructed')
    finally:raw_classes.close()
    rows,added=merge(base,native_rows)
    kernel={p:S.digest(S.ROOT/p)['sha256'] for p in frames['kernel_sha256']}
    S.check(kernel==frames['kernel_sha256'],'Native overlay frame runtime implementation changed')
    return dict(base=identity,base_frame_index=S.artifact(frame_index),replaced_data_assembly=S.artifact(base_assembly),
        replaced_data_object=S.artifact(base_object),runtime_kernel_sha256=kernel,base_rows=len(base),rows=[list(r) for r in rows],
        original_native_declarations=sorted(natives,key=lambda n:n['id']),added_native_ids=added)


def verify(path, batch, plan):
    path=Path(path).resolve();S.check(path.is_relative_to(S.ART),'Native overlay must remain in project .boom')
    m=S.read(path);expected=index(batch,plan)
    S.check(m['source']==expected and m['tool_sources']==tools(),'Native overlay source/tool identity changed')
    S.check((m['schema'],m['pool_abi'],m['pool_bytes'],m['method_row_bytes'])==(1,3,48,32),
            'Native frame overlay ABI changed')
    for key in ('all_native_frames','stack_roots','automatic_gc','linked','executed','game_started'):
        S.check(m[key] is False,'Native frame metadata overclaims execution: '+key)
    S.check(m['native_implementations_added']==0,'Frame metadata cannot provide native implementations')
    asm=S.checked(m['assembly']);obj=S.checked(m['object'])
    S.check(asm.parent==path.parent and obj.parent==path.parent and
            asm.read_text(encoding='utf-8')==assembly(expected['rows']),'Native frame overlay ASM changed')
    S.check(S.artifact(m['assembler']['path'])==m['assembler'],'Native overlay assembler changed')
    coff=S.module('native_overlay_actual_coff','verify-batch-assembly.py')
    S.check(coff.coff_symbols(obj)==symbols(expected['rows']),'Native frame overlay actual COFF differs')
    return dict(verified=True,scope='original_native_frame_rows_and_actual_COFF_only',
        manifest=str(path),manifest_sha256=S.digest(path)['sha256'],verifier_sha256=S.digest(Path(__file__))['sha256'],
        pool_abi=3,base_rows=expected['base_rows'],rows=len(expected['rows']),
        original_native_declarations=len(expected['original_native_declarations']),new_native_rows=len(expected['added_native_ids']),
        base_Java_ASM_and_COFF_modified=False,all_native_frames=False,linked=False,executed=False,game_started=False)


def build(batch,plan,output,assembler):
    output=Path(output).resolve();assembler=Path(assembler).resolve()
    S.check(output.is_relative_to(S.ART) and not output.exists(),'Native overlay needs a fresh isolated .boom directory')
    source=index(batch,plan);tool_identity=tools();assembler_identity=S.artifact(assembler)
    output.mkdir(parents=True)
    asm=output/'frames.asm';obj=output/'frames.obj';asm.write_text(assembly(source['rows']),encoding='utf-8')
    with (output/'assembler.log').open('wb') as log:
        result=subprocess.run([str(assembler),'/nologo','/c','/Fo'+str(obj),str(asm)],stdout=log,stderr=subprocess.STDOUT)
    S.check(result.returncode==0,'Native frame overlay assembly failed; inspect assembler.log')
    S.check(S.artifact(assembler)==assembler_identity and tools()==tool_identity,'Native overlay tools changed during assembly')
    m=dict(schema=1,pool_abi=3,pool_bytes=48,method_row_bytes=32,source=source,tool_sources=tool_identity,
        assembler=assembler_identity,assembly=S.artifact(asm),object=S.artifact(obj),native_implementations_added=0,
        all_native_frames=False,stack_roots=False,automatic_gc=False,linked=False,executed=False,game_started=False)
    S.write(output/'overlay.json',m)
    return output/'overlay.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch',type=Path,required=True);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--output',type=Path);p.add_argument('--assembler',type=Path);p.add_argument('--verify',type=Path)
    a=p.parse_args()
    if a.verify:
        proof=verify(a.verify,a.batch,a.plan);S.write(a.verify.with_name('verification.json'),proof);print(json.dumps(proof))
    else:
        p.error('--output and --assembler are required') if not a.output or not a.assembler else None
        print(build(a.batch,a.plan,a.output,a.assembler))
