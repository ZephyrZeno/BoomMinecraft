"""Canonical source/COFF proof for a separate real self-jimage module variant."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location('jimage_module_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


S=module('runtime-provider-source');C=module('native-library-jimage-source')
O=module('native-library-source-candidate');J=module('jimage-native-map-candidate')
KERNEL=ROOT/'native/providers/native_library_jimage.asm.inc'


def contract(state_file,bridge_file):
    bridge=S.read(bridge_file)
    S.check(J.verify(bridge_file)==S.read(Path(bridge_file).with_name('verification.json')),
        'Current original source JIMAGE bridge proof required')
    state=S.read(state_file)
    S.check(bridge['metadata']['input_state']==S.artifact(state_file) and state['tool_sources']==S.tools_identity(),
        'Jimage module/bridge must use the same current original source input')
    base,summary,classes=S.base(Path(state['batch']),Path(state['plan']));source=C.index(summary,classes,S)
    S.check(base==bridge['metadata']['base'],'Jimage module/bridge source base differs')
    frame=S.read(S.checked(bridge['metadata']['frame_overlay']['manifest']))
    natives={row['id']:row for row in frame['source']['original_native_declarations']}
    for row in source['methods']:
        original=natives[row['method']]
        S.check(original['flags']&32 and not original['flags']&128 and all(original[k]==row[k] for k in
            ('class_id','class_sha256','loader','source_id','name','descriptor','access')),
            'Original source library native declaration/frame differs')
    runtime=S.checked(bridge['metadata']['runtime']);runtime_meta=S.read(runtime.with_name('runtime.json'))
    kernels={'native/runtime/'+name:S.digest(ROOT/'native/runtime'/name)['sha256'] for name in C.KERNELS}
    S.check(all(runtime_meta['sources'].get(name)==sha for name,sha in kernels.items()),
        'Original library runtime kernel source changed')
    return dict(base=base,input_state=S.artifact(state_file),source=source,policy=C.POLICY,
        bridge=dict(candidate=S.artifact(bridge_file),verification=S.artifact(Path(bridge_file).with_name('verification.json')),
            object=bridge['object']),frame_overlay=bridge['metadata']['frame_overlay'],runtime=S.artifact(runtime),
        runtime_kernel_sha256=kernels,original_input_namespace=state['tool_sources'],
        source_helpers={name:S.artifact(ROOT/'scripts'/name) for name in
            ('native-library-source.py','native-library-helpers-source.py','native-library-source-candidate.py',
             'file-bootstrap-source.py','verify-batch-frames.py','test-file-output-standard.py')},
        input_state_status=state['status'],input_runtime_acceptance_complete=state['runtime_acceptance_complete'])


def assembly(meta):
    source=meta['source'];original,exports,imports=O.assembly(dict(source=source['base_source']))
    old_data=C.N.data(source['base_source'])
    S.check(original.count(old_data)==1 and original.endswith('\nEND\n'),
        'Original net/nio producer envelope/data changed')
    text=original.replace(old_data,C.data(source),1).removesuffix('END\n')
    tail=' jmp '+C.N.SERVICE+'\n'
    S.check(text.count(tail)==4,'Exactly the four original source adapter tails must be rerouted')
    text=text.replace(tail,' jmp '+C.SERVICE+'\n')
    procs,data=C.native_imports(source);extra=(procs|data)-imports
    text=text.replace('option casemap:none\n','option casemap:none\n'+''.join(
        f'EXTERN {name}:{"PROC" if name in procs else "BYTE"}\n' for name in sorted(extra)),1)
    text+=C.extension(source)+KERNEL.read_text(encoding='utf-8')+'\nEND\n'
    exports|=C.CONTROL|{C.SERVICE};imports|=extra
    return text,exports,imports,original


def old_machine_prefix(actual_path,old_path,methods):
    """Actual original code stays equal except the four native adapter jumps.

    All old code precedes the appended independent dispatcher/lifecycle. This
    compares real bytes and relocation targets, masking exactly each confirmed
    E9 operand which changes from old service to the new dispatcher.
    """
    T=module('test-file-output-standard')
    actual=T.coff_protocol(Path(actual_path));old=T.coff_protocol(Path(old_path))
    def symbols(path):
        raw=Path(path).read_bytes();_,count,_,at,n,_,_=struct.unpack_from('<HHIIIHH',raw)
        strings=at+n*18;result={};i=0
        while i<n:
            name,value,section,_,storage,aux=struct.unpack_from('<8sIhHBB',raw,at+i*18)
            if name[:4]==b'\0'*4:
                start=strings+struct.unpack_from('<I',name,4)[0];name=raw[start:raw.index(b'\0',start)]
            else:name=name.rstrip(b'\0')
            if storage==2 and section>0:
                section_name=raw[20+(section-1)*40:28+(section-1)*40].rstrip(b'\0').decode('ascii')
                result[name.decode('ascii')]=(section_name,value)
            i+=aux+1
        return result
    a_symbols=symbols(actual_path);o_symbols=symbols(old_path);masks=[]
    for row in methods:
        name=f"boom_m{row['method']}_native"
        S.check(a_symbols[name]==o_symbols[name],'Original native adapter placement changed')
        section,offset=o_symbols[name];masks.append((section,offset+14,offset+18))
    old_by={name:(data,relocs) for name,data,relocs in old};actual_by={name:(data,relocs) for name,data,relocs in actual}
    sizes={}
    for name,(raw,relocs) in old_by.items():
        if not name.startswith('.text'):continue
        ob=bytearray.fromhex(raw);ab=bytearray.fromhex(actual_by[name][0])[:len(ob)]
        S.check(len(ab)==len(ob),'Appended module truncated original code')
        for section,start,end in masks:
            if section!=name:continue
            S.check(ob[start-1]==ab[start-1]==0xE9,'Adapter change must be precisely its near JMP operand')
            ob[start:end]=ab[start:end]=b'\0'*4
        S.check(ab==ob,'An original net/nio instruction outside adapter JMPs changed')
        ar=[r for r in actual_by[name][1] if r[0]<len(ob)]
        # The old service is local, so these JMPs are normally assembler-fixed.
        # If a tool emits relocations, normalize only that exact allowed target.
        ar=[(offset,C.N.SERVICE if target==C.SERVICE and any(sec==name and lo==offset for sec,lo,_ in masks) else target,kind)
            for offset,target,kind in ar]
        S.check(ar==relocs,'An original net/nio relocation target changed')
        sizes[name]=len(ob)
    S.check(sizes,'Original lifecycle executable section is missing')
    return dict(original_code_prefix_bytes=sizes,changed_native_adapter_JMP_operands=4,
        other_original_instruction_bytes_and_relocations_equal=True)


def verify(path):
    value=S.read(path);meta=value['metadata']
    S.check(value.get('family')=='source-native-library-self-jimage-variant' and
        all(value.get(k) is False for k in ('registered','linked','executed','game_started')),
        'Independent unregistered jimage module variant scope differs')
    S.check(meta==contract(S.checked(meta['input_state']),S.checked(meta['bridge']['candidate'])),
        'Jimage module current source contract changed')
    for key,file in [('kernel',KERNEL),('model',ROOT/'scripts/native-library-jimage-source.py'),('tool',Path(__file__))]:
        S.check(value[key]==S.artifact(file),'Jimage module source changed: '+key)
    text,exports,imports,old=assembly(meta)
    S.check(value['exports']==sorted(exports) and value['imports']==sorted(imports) and
        S.checked(value['assembly']).read_text(encoding='utf-8')==text and
        O.A.coff_symbols(S.checked(value['object']),C.FOREIGN)==(exports,imports),
        'Jimage module canonical ASM or actual symbols changed')
    assembler=Path(value['assembler']['path']);S.check(S.artifact(assembler)==value['assembler'],'Jimage module assembler changed')
    fresh=S.ART/'jimage-native-map/library-machine-checks'/uuid4().hex;fresh.mkdir(parents=True)
    objs=[]
    for name,body in [('canonical',text),('original-net-nio',old)]:
        asm=fresh/(name+'.asm');obj=asm.with_suffix('.obj');asm.write_text(body,encoding='utf-8')
        with asm.with_suffix('.log').open('xb') as log:
            subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        objs.append(obj)
    T=module('test-file-output-standard');actual=T.coff_protocol(S.checked(value['object']));expected=T.coff_protocol(objs[0])
    S.check(actual==expected,'Jimage module actual code/data/unwind/all relocations differ from canonical')
    reuse=old_machine_prefix(S.checked(value['object']),objs[1],meta['source']['methods'])
    proof=dict(schema=1,verified=True,scope='original_NativeLibraries_self_jimage_source_frame_COFF_variant_only',
        candidate=S.artifact(path),normalized_COFF_sha256=hashlib.sha256(json.dumps(actual,separators=(',',':')).encode()).hexdigest(),
        original_net_nio_reuse=reuse,standard_JNI_addresses=False,external_JDK_Dynamic_Load=False,
        module_readiness_requires_real_attached_Thread_and_map_owner=True,
        original_System_loadLibrary_execution_not_implied=True,registered=False,linked=False,executed=False,game_started=False)
    S.write(fresh/'verification.json',proof);return proof


def build(state,bridge,assembler,output):
    output=Path(output).resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh jimage module output required')
    meta=contract(state,bridge);output.mkdir(parents=True);text,exports,imports,_=assembly(meta)
    asm,obj=output/'provider.asm',output/'provider.obj';asm.write_text(text,encoding='utf-8')
    with (output/'assembler.log').open('xb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    path=output/'candidate.json'
    S.write(path,dict(schema=1,family='source-native-library-self-jimage-variant',metadata=meta,kernel=S.artifact(KERNEL),
        model=S.artifact(ROOT/'scripts/native-library-jimage-source.py'),tool=S.artifact(Path(__file__)),assembler=S.artifact(assembler),
        assembly=S.artifact(asm),object=S.artifact(obj),exports=sorted(exports),imports=sorted(imports),
        registered=False,linked=False,executed=False,game_started=False))
    S.write(output/'verification.json',verify(path));return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--bridge',type=Path,required=True);parser.add_argument('--assembler',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    print(build(args.state.resolve(),args.bridge.resolve(),args.assembler.resolve(),args.output.resolve()))
