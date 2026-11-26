"""Rebuild ABI3 frame identities/annotations from original class bytes; no execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import zipfile


def check(value, message):
    if not value: raise ValueError(message)


class Reader:
    def __init__(self, data): self.data, self.at = data, 0
    def take(self, n):
        check(0 <= n <= len(self.data)-self.at, 'Truncated original class attribute')
        result=self.data[self.at:self.at+n]; self.at+=n; return result
    def number(self, n): return int.from_bytes(self.take(n), 'big')
    def end(self): check(self.at == len(self.data), 'Trailing original class attribute data')


def modified_utf8(data):
    text=data.replace(b'\xc0\x80', b'\0').decode('utf-8', 'surrogatepass')
    return text.encode('utf-16-le', 'surrogatepass').decode('utf-16-le', 'surrogatepass')


def original_methods(data):
    r=Reader(data);check(r.number(4)==0xcafebabe, 'Original class magic differs')
    r.take(4); count=r.number(2); cp=[None]*count; i=1
    while i<count:
        tag=r.number(1)
        if tag==1: cp[i]=modified_utf8(r.take(r.number(2)))
        elif tag in (3,4): r.take(4)
        elif tag in (5,6): r.take(8);i+=1
        elif tag in (7,8,16,19,20): cp[i]=r.number(2)
        elif tag in (9,10,11,12,17,18): r.take(4)
        elif tag==15: r.take(3)
        else: raise ValueError('Unknown original class constant tag')
        i+=1
    def utf(i):
        check(0<i<count and isinstance(cp[i],str), 'Original annotation/name is not UTF8');return cp[i]
    def attributes(reader):
        return [(utf(reader.number(2)),reader.take(reader.number(4))) for _ in range(reader.number(2))]
    def annotation(reader, depth=0):
        check(depth<64, 'Annotation nesting exceeds source bound')
        name=utf(reader.number(2))
        for _ in range(reader.number(2)):
            utf(reader.number(2)); value(reader,depth+1)
        return name
    def value(reader,depth):
        check(depth<64, 'Annotation nesting exceeds source bound')
        tag=chr(reader.number(1))
        if tag in 'BCDFIJSZsc': reader.take(2)
        elif tag=='e': reader.take(4)
        elif tag=='@': annotation(reader,depth+1)
        elif tag=='[':
            for _ in range(reader.number(2)): value(reader,depth+1)
        else: raise ValueError('Unknown original annotation value')
    r.number(2);this=r.number(2);r.number(2)
    check(0<this<count and isinstance(cp[this],int), 'Original class name missing')
    name=utf(cp[this]);r.take(2*r.number(2))
    for _ in range(r.number(2)): r.take(6);attributes(r)
    methods=[]
    for _ in range(r.number(2)):
        access=r.number(2);method_name=utf(r.number(2));desc=utf(r.number(2));code=None;annotations=[]
        for kind,payload in attributes(r):
            a=Reader(payload)
            if kind=='Code':
                check(code is None, 'Duplicate original Code')
                locals_stack=(a.number(2),a.number(2));body=a.take(a.number(4))
                a.take(8*a.number(2));attributes(a);a.end()
                code=(body,locals_stack[0],locals_stack[1])
            elif kind=='RuntimeVisibleAnnotations':
                annotations.extend(annotation(a) for _ in range(a.number(2)));a.end()
        methods.append(dict(name=method_name,descriptor=desc,access=access,code=code,annotations=annotations))
    attributes(r);r.end();return name,methods


WANTED={('java/lang/Class','forName0','(Ljava/lang/String;ZLjava/lang/ClassLoader;Ljava/lang/Class;)Ljava/lang/Class;'),
        ('java/lang/ClassLoader','findBootstrapClass','(Ljava/lang/String;)Ljava/lang/Class;'),
        ('jdk/internal/reflect/Reflection','getCallerClass','()Ljava/lang/Class;')}


def flags(owner, method, trusted, generated, accessor):
    annotations=method['annotations'] if trusted else ()
    mh=trusted and owner=='java/lang/invoke/MethodHandle' and method['name'] in (
        'invoke','invokeExact','invokeBasic','linkToVirtual','linkToStatic','linkToSpecial','linkToInterface','linkToNative')
    ignored=(accessor or mh or 'Ljava/lang/invoke/LambdaForm$Compiled;' in annotations or
             (trusted and (owner,method['name'],method['descriptor'])==('java/lang/reflect/Method','invoke','(Ljava/lang/Object;[Ljava/lang/Object;)Ljava/lang/Object;')))
    return (int(method['name']=='<init>') | (int(method['name']=='fillInStackTrace')<<1) | (int(generated)<<2) |
            (int('Ljdk/internal/reflect/CallerSensitive;' in annotations)<<3) |
            (int('Ljdk/internal/vm/annotation/Hidden;' in annotations)<<4) | (int(bool(method['access']&0x100))<<5) | (int(ignored)<<6))


def native_adapter(method, class_id, pool, service, operation):
    i=method
    return f".code\nboom_m{i} PROC FRAME\n sub rsp,120\n .allocstack 120\n .endprolog\n mov QWORD PTR [rsp+32],rcx\n mov QWORD PTR [rsp+40],rdx\n test rcx,rcx\n jz boom_m{i}_zero\n cmp DWORD PTR [rcx],0\n jne boom_m{i}_zero\n lea rcx,boom_class{class_id}\n mov rdx,QWORD PTR [rsp+32]\n call boom_class_ensure32\n test eax,eax\n jnz boom_m{i}_zero\n mov rcx,QWORD PTR [rsp+32]\n cmp DWORD PTR [rcx+12],128\n jae boom_m{i}_limit\n inc DWORD PTR [rcx+12]\n mov QWORD PTR [rsp+56],0\n lea rcx,boom_trace_pool\n lea rdx,[rsp+56]\n lea r8,boom_trace_method{i}\n mov r9,QWORD PTR [rsp+32]\n call boom_trace_enter\n test eax,eax\n jnz boom_m{i}_entered_error\n mov rcx,QWORD PTR [rsp+32]\n mov rdx,QWORD PTR [rsp+40]\n call boom_m{i}_native\n jmp boom_m{i}_leave\nboom_m{i}_entered_error:\n xor eax,eax\nboom_m{i}_leave:\n mov QWORD PTR [rsp+48],rax\n lea rcx,boom_trace_pool\n lea rdx,[rsp+56]\n mov r8,QWORD PTR [rsp+32]\n call boom_trace_leave\n mov rcx,QWORD PTR [rsp+32]\n dec DWORD PTR [rcx+12]\n cmp DWORD PTR [rcx],0\n jne boom_m{i}_zero\n mov rax,QWORD PTR [rsp+48]\n add rsp,120\n ret\nboom_m{i}_limit:\n mov DWORD PTR [rcx],10\nboom_m{i}_zero:\n xor eax,eax\n add rsp,120\n ret\nboom_m{i} ENDP\nboom_m{i}_native PROC\n lea r8,{pool}\n mov r9d,{operation}\n jmp {service}\nboom_m{i}_native ENDP\n"


def java_frame(body, method, max_locals, max_stack, pcs):
    base=64+max(max_stack,16)*8+max_locals*8+max_stack*8
    size=((base+64+8+15)//16)*16-8
    required=[f'mov QWORD PTR [rsp+{base}], 0',f'lea rdx, [rsp+{base}]',
              f'lea r8, boom_trace_method{method}',f'mov rdx, QWORD PTR [rsp+{base+56}]',
              f'mov QWORD PTR [rsp+{base+48}], rax',f'mov rax, QWORD PTR [rsp+{base+48}]',
              f'sub rsp, {size}',f'.allocstack {size}',f'add rsp, {size}']
    check(all(s in body for s in required) and body.count('call boom_trace_enter')==1 and
          body.count('call boom_trace_leave')==1, 'Generated Java frame enter/leave/layout differs')
    writes=[int(m[1]) for m in re.finditer(r'mov DWORD PTR \[rsp\+'+str(base+24)+r'\], (\d+)\n',body)]
    check(writes==list(pcs), 'Generated Java frame PC map differs from source reference maps')
    if size>=4096:
        check(f'mov eax, {size}\n    call boom_stack_probe\n    sub rsp, {size}' in body,
              'Large Java frame lacks argument-preserving page probe')
    else: check('call boom_stack_probe' not in body, 'Unexpected small-frame stack probe')


def verify(root, summary, plan, inventory, emitted, artifact, coff_symbols, file_digest):
    s=summary['frames'];plan=Path(plan);source=json.loads((plan/'summary.json').read_text())
    classes=[json.loads(l) for l in (plan/'classes.jsonl').read_text().splitlines()]
    catalog_path=Path(s['original_system_catalog']['path'])
    check(file_digest(catalog_path)==s['original_system_catalog']['digest'], 'Frame original system catalog changed')
    system=json.loads(catalog_path.read_text())
    check(system['input_fingerprint']==summary['input_fingerprint'] and system['fingerprint']==source['jdk_fingerprint'],
          'Frame original JDK identity differs')
    with zipfile.ZipFile(artifact(root,summary['runtime_metadata']['index'],'runtime-metadata')) as z:
        available={json.loads(l)['id'] for l in z.read('types.jsonl').splitlines()}
    spec=importlib.util.spec_from_file_location('frame_source_hierarchy',Path(__file__).with_name('verify-batch-metadata.py'))
    hierarchy=importlib.util.module_from_spec(spec);spec.loader.exec_module(hierarchy)
    lookup,_,parents,_=hierarchy.source_model(classes)
    accessor=lookup('bootstrap','jdk/internal/reflect/MethodAccessorImpl')
    rows=[];natives=[];java=unavailable=native_count=0;archives={}
    try:
        with zipfile.ZipFile(artifact(root,s['index'],'frames')) as z:
            check(z.namelist()==['methods.jsonl','natives.jsonl'], 'Frame index entries differ')
            with z.open('methods.jsonl') as records:
                for c in classes:
                    origin=c['origin'];trusted=origin['loader'] in ('bootstrap','platform') and origin['source_id'].startswith('jdk:') and not origin.get('generated')
                    if origin['source_id'].startswith('jdk:'):
                        raw=(catalog_path.parent/'image'/origin['jar_entry']).read_bytes()
                    else:
                        key=origin['source_id']
                        if key not in archives:
                            a=s['original_input_files'][key];p=Path(a['path']);check(file_digest(p)==a['digest'], 'Frame source archive changed')
                            archives[key]=zipfile.ZipFile(p)
                        raw=archives[key].read(origin['jar_entry'])
                    check(hashlib.sha256(raw).hexdigest()==origin['sha256'], 'Frame original class bytes changed')
                    owner,methods=original_methods(raw)
                    check(owner==c['name'] and len(methods)==len(c['method_ids']), 'Frame original method inventory differs')
                    parent=c['id'];ignored=False;visited=set()
                    while parent is not None and parent not in visited:
                        visited.add(parent)
                        if parent==accessor: ignored=True;break
                        parent=parents.get(parent)
                    for i,m in zip(c['method_ids'],methods):
                        code=m['code'];code_sha=hashlib.sha256(code[0]).hexdigest() if code else None
                        check(inventory[i][:6]==(c['id'],m['name'],m['descriptor'],origin['sha256'],code_sha,len(code[0]) if code else 0) and
                              inventory[i][8]==m['access'], 'Frame original method differs from locked plan')
                        if code: check(inventory[i][6:8]==(code[2],code[1]), 'Frame original Code stack/locals differ')
                        if code is None and (owner,m['name'],m['descriptor']) not in WANTED: continue
                        f=flags(owner,m,trusted,bool(origin.get('generated')),ignored)
                        if c['id'] not in available: f|=128;unavailable+=1
                        expected=dict(id=i,class_id=c['id'],class_sha256=origin['sha256'],loader=origin['loader'],source_id=origin['source_id'],class_name=owner,
                            name=m['name'],descriptor=m['descriptor'],access=m['access'],code_sha256=code_sha,code_length=len(code[0]) if code else 0,
                            annotations=m['annotations'],flags=f,assembly_emitted=i in emitted)
                        check(json.loads(next(records,b'null'))==expected, 'Frame source annotations/flags/identity differ: '+str(i))
                        rows.append((i,f,c['id'],expected['code_length']));java+=code is not None;native_count+=code is None
                        if (origin['loader'],owner,m['name'],m['descriptor'])==('bootstrap','jdk/internal/reflect/Reflection','getCallerClass','()Ljava/lang/Class;'):
                            check(m['access']==0x109 and origin['source_id']=='jdk:java.base' and f&40==40, 'Caller source native declaration changed')
                            natives.append(dict(method=i,class_id=c['id'],class_sha256=origin['sha256'],name=m['name'],descriptor=m['descriptor'],access=0x109,operation=0,assembly_unit=1))
                check(not records.read(), 'Extra frame source records')
            check(len(natives)==1 and [json.loads(l) for l in z.read('natives.jsonl').splitlines()]==natives, 'Caller native source index differs')
    finally:
        for z in archives.values(): z.close()
    # The source-native index names the unit that actually defines its adapter.
    n=natives[0];method=n['method'];class_id=n['class_id']
    def data():
        yield '.const\nALIGN 8\nPUBLIC boom_trace_methods\nboom_trace_methods LABEL BYTE\n'
        for i,f,c,length in rows:
            declaring='0' if f&128 else f'OFFSET boom_t{c}'
            yield f'PUBLIC boom_trace_method{i}\nboom_trace_method{i} DWORD {i},{f}\n QWORD {declaring}\n DWORD {length},{c}\n QWORD 0\n'
        yield f'.data\nALIGN 8\nPUBLIC boom_trace_pool\nboom_trace_pool DWORD 05452504Ch,3,0,0FFFFFFFFh\n DWORD {len(rows)},0\n QWORD OFFSET boom_trace_methods,0,0\n.code\nPUBLIC boom_release_trace_pool\nboom_release_trace_pool PROC\n lea rcx,boom_trace_pool\n jmp boom_trace_release\nboom_release_trace_pool ENDP\n'
        yield '\n'  # Rust writeln appends a newline to the pool text, which already ends in one.
    caller=f'.const\nALIGN 8\nPUBLIC boom_java_caller_pool\nboom_java_caller_pool DWORD 04A434352h,1\n QWORD OFFSET boom_java_class_pool,OFFSET boom_trace_pool\n DWORD {method},{class_id},32,32,0,0\n QWORD 0,0\n'+native_adapter(method,class_id,'boom_java_caller_pool','boom_java_caller',0)
    check(len(s['units'])==2, 'Frame data/native unit split differs')
    defined=set();undefined=set()
    for index,parts in enumerate((data(),iter([caller]))):
        expected_hash=hashlib.sha256();length=0
        for part in parts: b=part.encode();expected_hash.update(b);length+=len(b)
        unit=s['units'][index];text=artifact(root,unit['assembly'],'frames').read_text();body=text.partition('.code\n')[2][:-5]
        check(unit['id']==index and unit['body_bytes']==length and text.endswith('\nEND\n') and
              hashlib.sha256(body.encode()).digest()==expected_hash.digest(), 'Frame generated MASM differs from original methods')
        check(unit['object'] and not unit['assembler_diagnostic'], 'Frame object unavailable')
        d,x=coff_symbols(artifact(root,unit['object'],'frames'))
        if index==0:
            exports={'boom_trace_methods','boom_trace_pool','boom_release_trace_pool'}|{f'boom_trace_method{r[0]}' for r in rows}
            imports={'boom_trace_release'}|{f'boom_t{r[2]}' for r in rows if not r[1]&128}
        else:
            exports={'boom_java_caller_pool',f'boom_m{method}',f'boom_m{method}_native'}
            imports={'boom_java_class_pool','boom_trace_pool',f'boom_trace_method{method}',f'boom_class{class_id}',
                     'boom_class_ensure32','boom_trace_enter','boom_trace_leave','boom_java_caller'}
        check(d==exports and x==imports, 'Frame COFF source definitions/imports differ');defined.update(d);undefined.update(x)
    expected=dict(abi=3,pool_bytes=48,node_bytes=48,method_row_bytes=32,methods=len(rows),java_methods=java,native_frame_methods=native_count,
                  generated_java_frames=len(emitted),unavailable_declaring_types=unavailable,native_methods=1,caller_pool_bytes=64,native_upcall_frames=2)
    check(all(s[k]==v for k,v in expected.items()) and s['every_emitted_java_method_traced'], 'Frame source counts/ABI differ')
    check(not any(s[k] for k in ('all_native_frames','stack_roots','automatic_gc','game_started')), 'Frame verification overclaims execution/roots')
    kernels={'native/runtime/'+n for n in ('frames.asm','stack_probe.asm','java_caller.asm','java_classes.asm','classes32.asm')}
    check(set(s['kernel_sha256'])==kernels, 'Frame kernel dependencies differ')
    for path,h in s['kernel_sha256'].items(): check(file_digest(Path(__file__).resolve().parents[1]/path)['sha256']==h, 'Frame ASM kernel changed')
    return dict(verified=True,original_method_records=len(rows),generated_java_frames=len(emitted),native_frame_methods=native_count,
                caller_native_methods=1,execution_verified=False,all_native_frames=False,stack_roots=False,game_started=False),defined,undefined,{method}
