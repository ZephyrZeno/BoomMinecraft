"""Check every available original static synchronized envelope and Java body."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def check(ok,message):
    if not ok:raise ValueError(message)


def expected(i,owner):
    return f'''boom_m{i} PROC FRAME
    sub rsp, 88
    .allocstack 88
    .endprolog
    mov QWORD PTR [rsp+48], rcx
    mov QWORD PTR [rsp+56], rdx
    lea rcx, boom_class{owner}
    mov rdx, QWORD PTR [rsp+48]
    call boom_class_ensure32
    test eax, eax
    jnz boom_m{i}_monitor_propagate
    mov rcx, QWORD PTR [rsp+48]
    lea rdx, boom_java_class_pool
    mov r8d, {owner}
    call boom_java_class_load
    mov r10, QWORD PTR [rsp+48]
    cmp DWORD PTR [r10], 0
    jne boom_m{i}_monitor_error
    mov QWORD PTR [rsp+64], rax
    mov rcx, QWORD PTR [boom_heap_ptr]
    mov rdx, rax
    mov r8, QWORD PTR [rsp+48]
    call boom_monitor_enter
    test eax, eax
    jnz boom_m{i}_monitor_error
    mov rcx, QWORD PTR [rsp+48]
    mov rdx, QWORD PTR [rsp+56]
    call boom_m{i}_body
    mov QWORD PTR [rsp+72], rax
    mov rcx, QWORD PTR [boom_heap_ptr]
    mov rdx, QWORD PTR [rsp+64]
    mov r8, QWORD PTR [rsp+48]
    call boom_monitor_exit
    test eax, eax
    jnz boom_m{i}_monitor_error
    mov rax, QWORD PTR [rsp+72]
    jmp boom_m{i}_monitor_done
boom_m{i}_monitor_error:
    mov rcx, QWORD PTR [rsp+48]
    cmp DWORD PTR [rcx], 16
    je boom_m{i}_monitor_keep
    mov DWORD PTR [rcx+4], 0
    mov DWORD PTR [rcx+8], {i}
    call boom_exception_materialize
boom_m{i}_monitor_keep:
    xor eax, eax
boom_m{i}_monitor_propagate:
    xor eax, eax
boom_m{i}_monitor_done:
    add rsp, 88
    ret
boom_m{i} ENDP
'''


def verify(batch,previous,plan,compiler):
    batch,previous,plan=map(lambda p:Path(p).resolve(),(batch,previous,plan))
    check(all(p.is_relative_to(ROOT/'.boom') for p in (batch,previous,plan)),'Monitor verification must use project artifacts')
    new,old=read(batch/'summary.json'),read(previous/'summary.json');p=read(plan/'summary.json')
    check(new['schema']==old['schema']==23 and new['compiler_sha256']==sha(compiler),'Normal monitor compiler/schema differs')
    check(new['input_fingerprint']==old['input_fingerprint']==p['input_fingerprint'] and new['ir_identity']==old['ir_identity'],
            'Normal monitor source input/IR differs')
    methods_path=Path(p['artifacts']['methods']['path']);check(sha(methods_path)==p['artifacts']['methods']['digest']['sha256'],'Original method plan changed')
    wanted={}
    for line in methods_path.open(encoding='utf-8'):
        m=json.loads(line)
        if m['access']&0x28==0x28 and m['code_sha256'] is not None:wanted.setdefault(m['class_id'],{})[m['id']]=m
    def declarations(summary):
        result={}
        for sh in summary['shards']:
            path=Path(sh['zip']['path']);check(sha(path)==sh['zip']['digest']['sha256'],'Monitor source class archive changed')
            with zipfile.ZipFile(path) as z:
                for name in z.namelist():
                    id_=int(Path(name).stem)
                    if id_ in wanted:result[id_]=(json.loads(z.read(name)),sh)
        return result
    before,after=declarations(old),declarations(new)
    spec=importlib.util.spec_from_file_location('normal_monitor_original_functions',ROOT/'scripts/batch-source.py');sources=importlib.util.module_from_spec(spec);spec.loader.exec_module(sources)
    cache=sources.Sources();rows=[];unavailable=[];checked_units=set()
    def function(summary,sh,m,label):
        unit=sh['units'][m['assembly_unit']];assembly=Path(unit['assembly']['path']);obj=Path(unit['object']['path'])
        if str(assembly) not in checked_units:
            check(sha(assembly)==unit['assembly']['digest']['sha256'] and sha(obj)==unit['object']['digest']['sha256'],'Monitor actual ASM/COFF changed')
            checked_units.add(str(assembly))
        return cache.function(assembly,label)
    for owner,declared in sorted(wanted.items()):
        a,ash=before[owner];b,bsh=after[owner];check(a['source_sha256']==b['source_sha256'],'Monitor declaring class changed')
        am={m['id']:m for m in a['methods']};bm={m['id']:m for m in b['methods']}
        for i,m in declared.items():
            x,y=am[i],bm[i]
            check(x['code_sha256']==y['code_sha256']==m['code_sha256'] and a['source_sha256']==m['class_sha256'],'Monitor original Java Code changed')
            check(x['assembly_emitted']==y['assembly_emitted'],'Monitor Java availability changed')
            if not y['assembly_emitted']:unavailable.append(i);continue
            wrapped=function(new,bsh,y,f'boom_m{i}');check(wrapped==expected(i,owner),'Normal static synchronized envelope differs: '+str(i))
            body_a=function(old,ash,x,f'boom_m{i}_body');body_b=function(new,bsh,y,f'boom_m{i}_body')
            check(body_a==body_b,'Original synchronized Java body changed: '+str(i))
            rows.append(dict(method=i,class_id=owner,name=m['symbol']['name'],descriptor=m['symbol']['descriptor'],code_sha256=m['code_sha256'],
                wrapper_sha256=hashlib.sha256(wrapped.encode()).hexdigest(),unchanged_Java_body_sha256=hashlib.sha256(body_b.encode()).hexdigest()))
    check(rows,'No original static synchronized envelopes checked')
    return dict(verified=True,scope='all_available_original_static_synchronized_envelopes_and_unchanged_Java_bodies_only',
        compiler_sha256=sha(compiler),batch_summary_sha256=sha(batch/'summary.json'),previous_batch_summary_sha256=sha(previous/'summary.json'),
        methods=len(rows),unavailable_source_methods=unavailable,rows=rows,normal_ClassPool_used=True,
        class_literal_metadata_abi=new['class_literals']['abi'],context_bytes=32,actual_runtime_executed=False,game_started=False)


if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('batch',type=Path);a.add_argument('--previous',type=Path,required=True);a.add_argument('--plan',type=Path,required=True);a.add_argument('--compiler',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    p=a.parse_args();r=verify(p.batch,p.previous,p.plan,p.compiler);check(not p.output.exists(),'Monitor proof already exists');p.output.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in r.items() if k!='rows'}))
