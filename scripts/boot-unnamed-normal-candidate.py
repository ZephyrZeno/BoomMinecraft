"""Build the source-bound BootLoader native and its one-slot normal JCLS extension."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile


def script(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S = script('runtime-provider-source')
IR = script('verify-translation-ir')
FR = script('verify-batch-frames')
F = script('file-bootstrap-source')
COFF = script('verify-batch-assembly')
BOOT = 'jdk/internal/loader/BootLoader'
MOD = 'java/lang/Module'
SYS = 'java/lang/System$2'
JLA = 'jdk/internal/access/JavaLangAccess'
MODULE = 'Ljava/lang/Module;'
LOADER = 'Ljava/lang/ClassLoader;'
DEFINE = '(' + LOADER + ')' + MODULE
ENABLE = '(' + MODULE + ')' + MODULE
PUBLISH = '(' + MODULE + ')V'
METHOD = 'setBootLoaderUnnamedModule0'
TEMPLATE = S.ROOT / 'native/providers/boot_unnamed_normal.asm.inc'
FIELDS = [('layer', 'Ljava/lang/ModuleLayer;', 0x12, 8, True),
          ('name', 'Ljava/lang/String;', 0x12, 8, True),
          ('loader', LOADER, 0x12, 8, True),
          ('descriptor', 'Ljava/lang/module/ModuleDescriptor;', 0x12, 8, True),
          ('enableNativeAccess', 'Z', 2, 1, False)]


def member(source, declaration, name, descriptor):
    [pair] = [(ident, m) for ident, m in zip(declaration['method_ids'], source.methods)
              if (m['name'], m['descriptor']) == (name, descriptor)]
    ident, m = pair
    code = source.code(m)
    return dict(method=ident, class_id=declaration['id'], class_sha256=declaration['origin']['sha256'],
                owner=source.name, name=name, descriptor=descriptor, access=m['access'],
                code_sha256=hashlib.sha256(code['bytes']).hexdigest() if code else None), code


def contract(batch, plan):
    summary, source, verification = S.read(batch/'summary.json'), S.read(plan/'summary.json'), S.read(batch/'verification.json')
    S.check(source['game_version'] == '1.21.1' and source['input_fingerprint'] == summary['input_fingerprint'] and
            verification['verified'] and all(verification[k]['verified'] for k in ('class_literals','class_state','frames')),
            'Verified normal 1.21.1 class roots, source frames and original plan required')
    classes = {}
    with S.checked(source['artifacts']['classes']).open(encoding='utf-8') as lines:
        for line in lines:
            c = json.loads(line)
            if c['name'] in (BOOT, MOD, SYS, MOD + '$EnableNativeAccess') and c['origin']['loader'] == 'bootstrap':
                S.check(c['origin']['source_id'] == 'jdk:java.base' and not c['origin'].get('generated'),
                        'Expected original bootstrap java.base classes')
                raw = IR.Source(S.original_class(summary,c))
                raw_fields = [{k:f[k] for k in ('name','descriptor','access')} for f in raw.fields]
                S.check(raw.name == c['name'] and len(raw.methods) == len(c['method_ids']) and raw_fields == c['fields'],
                        'Source class or field inventory differs')
                classes[c['name']] = c, raw
    boot, raw_boot = classes[BOOT]
    module, _ = classes[MOD]
    [static] = [i for i,f in enumerate(raw_boot.fields) if (f['name'],f['descriptor'],f['access']) ==
                ('UNNAMED_MODULE', MODULE, 0x1a)]
    native, code = member(raw_boot, boot, METHOD, PUBLISH)
    S.check(native['access'] == 0x10a and code is None, 'Original private static native contract differs')
    originals = []
    for owner,name,descriptor in [(BOOT,'<clinit>','()V'), (SYS,'defineUnnamedModule',DEFINE),
                                  (MOD,'<init>','(' + LOADER + ')V'), (SYS,'addEnableNativeAccess',ENABLE),
                                  (MOD,'implAddEnableNativeAccess','()' + MODULE),
                                  (MOD + '$EnableNativeAccess','trySetEnableNativeAccess','(' + MODULE + ')Z')]:
        c, raw = classes[owner]
        record, code = member(raw,c,name,descriptor)
        S.check(code and not record['access'] & 0x500, 'Source Java execution requires concrete bytecode')
        if owner == BOOT:
            instructions = {i['pc']:i for i in IR.stream(code['bytes'])}
            S.check(instructions[17]['opcode'] == 1 and instructions[59]['opcode'] == 0xb1,
                    'Expected bootstrap null loader and normal initializer return')
            for pc,op,who,n,d in [(18,0xb9,JLA,'defineUnnamedModule',DEFINE), (23,0xb3,BOOT,'UNNAMED_MODULE',MODULE),
                                  (27,0xb2,BOOT,'UNNAMED_MODULE',MODULE),(30,0xb9,JLA,'addEnableNativeAccess',ENABLE),
                                  (36,0xb2,BOOT,'UNNAMED_MODULE',MODULE),(39,0xb8,BOOT,METHOD,PUBLISH)]:
                i = instructions[pc]
                operand = i['operand']
                symbol = raw.member(operand['Interface']['constant'] if op == 0xb9 else operand['Constant'])
                S.check(i['opcode'] == op and (symbol['owner'],symbol['name'],symbol['descriptor']) == (who,n,d),
                        f'Original BootLoader bytecode binding differs at {pc}')
        originals.append(record)
    with S.checked(summary['layouts']).open(encoding='utf-8') as lines:
        layout = next(row for line in lines if (row := json.loads(line))['class_id'] == module['id'])
    fields = F.fields(module,layout,FIELDS,S)
    with zipfile.ZipFile(S.checked(summary['class_state']['index'])) as z, z.open('classes.jsonl') as lines:
        row = next(r for l in lines if (r := json.loads(l))['class_id'] == boot['id'])
    cell = next(f for f in row['fields'] if f['index'] == static)
    S.check(row['source_sha256'] == native['class_sha256'] and row['initializer'] == dict(method=originals[0]['method'],
            code_sha256=originals[0]['code_sha256'],assembly_emitted=True) and cell['reference'] and
            cell['declared_storage_bytes'] == 8 and cell['initial_bits'] == 0 and cell['constant'] is None and
            (cell['name'],cell['descriptor'],cell['access']) == ('UNNAMED_MODULE', MODULE, 0x1a),
            'Normal static root or original class initializer differs')
    jcls = summary['class_literals']
    mods, loaders = jcls['modules'], jcls['loader_keys']
    S.check(jcls['abi'] == 1 and loaders[0]=='bootstrap' and jcls['source_shape']['module_type']==module['id'] and
            [r['id'] for r in mods] == list(range(len(mods))) and (0,None) not in {(m['loader'],m['name']) for m in mods} and
            all(0 <= m['loader'] < len(loaders) for m in mods) and len(mods)<65536 and
            jcls['root_cells'] == jcls['type_capacity']+len(loaders)+len(mods), 'JCLS keys or strong-root span differs')
    return summary, dict(native=native, source_java=originals, owner=boot['id'], module_type=module['id'], static_index=static,
                         module_fields=fields, original_module_keys=mods, module_slot=len(mods), root_cells=jcls['root_cells'])


def pool_overlay(original, jcls):
    """All four changes affect JCLS data; no existing key, type record or Java method changes."""
    mods, nload = jcls['modules'], len(jcls['loader_keys'])
    nmod, nroot, ntype = len(mods), jcls['root_cells'], jcls['type_capacity']
    mask = jcls['reverse_slots']-1
    loader_table = 'boom_java_class_module_loaders LABEL DWORD\n' + ''.join(f" DWORD {r['loader']}\n" for r in mods)
    span = (f'boom_java_class_roots LABEL QWORD\n QWORD {ntype} DUP(?)\nPUBLIC boom_java_class_loader_roots\n'
            f'boom_java_class_loader_roots QWORD {nload} DUP(?)\nPUBLIC boom_java_class_module_roots\n')
    edits = [(f' DWORD {mask},{nload},{nmod},1\n', f' DWORD {mask},{nload},{nmod+1},1\n'),
             (f'boom_java_class_root_count QWORD {nroot}\n',f'boom_java_class_root_count QWORD {nroot+1}\n'),
             (loader_table+'.data?\n',loader_table+' DWORD 0\n.data?\n'),
             (span+f'boom_java_class_module_roots QWORD {nmod} DUP(?)\n',
              span+f'boom_java_class_module_roots QWORD {nmod+1} DUP(?)\n')]
    for before,after in edits:
        S.check(original.count(before)==1, 'Original normal JCLS data declaration differs: '+before[:60])
        original = original.replace(before,after,1)
    return original


def assembly(info):
    m, owner, mid = info['native']['method'], info['owner'], info['module_type']
    static=f"boom_s{owner}_{info['static_index']}"
    data={f'boom_class{owner}',static,f'boom_layout{mid}',f'boom_trace_method{m}','boom_java_class_pool',
          'boom_trace_pool','boom_heap_ptr'}
    procs={'boom_class_ensure32','boom_trace_enter','boom_trace_leave'}
    prefix='option casemap:none\n'+''.join(f'EXTERN {name}:BYTE\n' for name in sorted(data))
    prefix+=''.join(f'EXTERN {name}:PROC\n' for name in sorted(procs))
    prefix+=f'BUN_OWNER TEXTEQU <boom_class{owner}>\nBUN_STATIC TEXTEQU <{static}>\nBUN_LAYOUT TEXTEQU <boom_layout{mid}>\n'
    prefix+=f"BUN_SLOT EQU {info['module_slot']}\nBUN_MODULES EQU {info['module_slot']+1}\n"
    names={'layer':'LAYER','name':'NAME','loader':'LOADER','descriptor':'DESCRIPTOR','enableNativeAccess':'ENABLE'}
    prefix+=''.join(f"BUN_{names[f['name']]} EQU {f['offset']}\n" for f in info['module_fields'])
    return prefix+TEMPLATE.read_text()+f'\nPUBLIC boom_m{m}\nPUBLIC boom_m{m}_native\n'+FR.native_adapter(
        m,owner,'boom_java_class_pool','boom_boot_unnamed_normal',0)+'END\n'


def build(batch,plan,output,assembler):
    S.check(all(p.is_relative_to(S.ART) for p in (batch,plan,output)) and not output.exists(),
            'Verified inputs and fresh candidate output must be under .boom')
    summary, info = contract(batch,plan)
    [unit] = summary['class_literals']['units']
    source, original_object = S.checked(unit['assembly']), S.checked(unit['object'])
    S.check(S.digest(assembler)['sha256']==unit['assembler_cache']['assembler_sha256'],'Original MASM assembler differs')
    output.mkdir(parents=True)
    def assemble(name,body):
        asm,obj=output/(name+'.asm'),output/(name+'.obj')
        with asm.open('w',encoding='utf-8',newline='\n') as fp:
            fp.write(body)
        with (output/(name+'.log')).open('wb') as fp:
            subprocess.run([assembler,'/nologo','/c',f'/Fo{obj}',asm],stdout=fp,stderr=subprocess.STDOUT,check=True)
        return S.artifact(asm),S.artifact(obj)
    asm, provider = assemble('boot-unnamed',assembly(info))
    changed, table = assemble('class-module-table',pool_overlay(source.read_text(encoding='utf-8'),summary['class_literals']))
    S.check(COFF.coff_symbols(original_object)==COFF.coff_symbols(S.checked(table)), 'JCLS public/imported symbols changed')
    defs,imports=COFF.coff_symbols(S.checked(provider),{'GetCurrentThreadId'})
    native=f"boom_m{info['native']['method']}"
    S.check(defs=={native,native+'_native','boom_boot_unnamed_normal'} and 'boom_java_class_bind_module' in imports,
            'Missing original method or shared JCLS publication in real provider COFF')
    manifest=dict(schema=1,family='normal-boot-unnamed-module-candidate',batch=S.artifact(batch/'summary.json'),
        verification=S.artifact(batch/'verification.json'),plan=S.artifact(plan/'summary.json'),
        contract=info,assembler=S.artifact(assembler),template=S.artifact(TEMPLATE),tool=S.artifact(Path(__file__)),
        provider_assembly=asm,provider_object=provider,original_jcls_assembly=unit['assembly'],
        original_jcls_object=unit['object'],jcls_assembly=changed,jcls_object=table,added_key=dict(
            id=info['module_slot'],loader=0,name=None),exports=sorted(defs),imports=sorted(imports),
        gc_roots_after=info['root_cells']+1,shared_provider_registered=False,executed=False,game_started=False)
    S.write(output/'candidate.json',manifest)
    return output/'candidate.json'


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('batch','plan','output','assembler'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    print(build(*(getattr(args,key).resolve() for key in ('batch','plan','output','assembler'))))
