"""Build an isolated source-bound getDeclaredMethods0 candidate, without registration."""
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
    spec=importlib.util.spec_from_file_location('normal_methods_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


S=module('runtime-provider-source');C=module('normal-methods-source')
R=module('verify-batch-frames');A=module('verify-batch-assembly')
KERNEL=ROOT/'native/providers/normal_methods.asm.inc'


def source_scope(state):
    accepted=state['status']=='accepted'
    S.check(state['status'] in ('accepted','pending_runtime_acceptance') and
        state.get('current_source_provider_verification_complete') is True and
        state.get('runtime_acceptance_complete') is accepted and
        state.get('accepted_provider_set_published') is accepted,
        'Methods candidate requires an explicit verified accepted/pending source scope')
    return dict(input_state_status=state['status'],source_verified=True,
        input_runtime_acceptance_complete=accepted,candidate_runtime_acceptance_proven=False)


def contract(state_file):
    state=S.read(state_file);identity,summary,classes=S.base(Path(state['batch']),Path(state['plan']))
    scope=source_scope(state)
    S.check(state['batch_summary_sha256']==identity['batch_summary']['digest']['sha256'] and
        state['batch_verification_sha256']==identity['base_verification']['digest']['sha256'] and
        state['tool_sources']==S.tools_identity(),'Current verified original provider source required')
    meta=C.index(summary,classes,S);frame=Path(state['frame_manifest']);proof=frame.with_name('verification.json')
    receipt=S.read(proof);source=S.read(frame)['source']
    actual_frame=module('native-frame-overlay').verify(frame,Path(state['batch']),Path(state['plan']))
    S.check(actual_frame==receipt and receipt['verified'] and receipt['manifest_sha256']==S.digest(frame)['sha256'] and
        state['frame_verification_sha256']==S.digest(proof)['sha256'] and source['base']['batch_summary']==identity['batch_summary'],
        'Original native frame source/base identity differs')
    rows={r['id']:r for r in source['original_native_declarations']}
    for method in meta['methods']:
        row=rows[method['method']]
        S.check(row['flags']&32 and not row['flags']&128 and all(row[k]==method[k] for k in
            ('class_id','class_sha256','loader','source_id','name','descriptor','access')),
            'Original getDeclaredMethods0 native frame differs')
    runtime=Path(state['runtime']);runtime_meta=S.read(runtime/'runtime.json')
    kernels={'native/runtime/'+n:S.digest(ROOT/'native/runtime'/n)['sha256'] for n in C.KERNELS}
    S.check(S.digest(runtime/'boom-runtime.dll')['sha256']==state['runtime_sha256']==runtime_meta['sha256'] and
        all(runtime_meta['sources'][name]==sha for name,sha in kernels.items()),'Original assembly runtime kernels differ')
    return dict(base=identity,input_state=S.artifact(state_file),input_scope=scope,source=meta,policy=C.POLICY,
        frame_overlay=dict(manifest=S.artifact(frame),verification=S.artifact(proof)),
        runtime_kernel_sha256=kernels)


def assembly(meta):
    source=meta['source'];procs,data=C.native_imports(source);owner=source['owner']
    imports=procs|data|{'boom_class_ensure32',f'boom_class{owner}'}
    text='option casemap:none\n'+''.join(f'EXTERN {n}:{"PROC" if n in procs else "BYTE"}\n' for n in sorted(imports))
    text+=C.data(source)
    for method in source['methods']:
        ident=method['method'];text+=f'.code\nPUBLIC boom_m{ident}\nPUBLIC boom_m{ident}_native\n'
        text+=R.native_adapter(ident,owner,C.POOL,C.SERVICE,method['operation']).removeprefix('.code\n')
    text+=KERNEL.read_text(encoding='utf-8')+'\nEND\n'
    exports=C.CONTROL|{C.POOL,C.SERVICE}|{f"boom_m{m['method']}{suffix}" for m in source['methods'] for suffix in ('','_native')}
    return text,exports,imports


def normalized_coff(path):
    """Seal execution bytes, flags, full symbols and normalized relocation targets.

    This reader streams private metadata symbols instead of retaining millions
    of Python dictionaries for the original method table. Only assembler file
    names/debug sections and physical table offsets/timestamp are excluded.
    """
    raw=Path(path).read_bytes();S.check(len(raw)>=20,'Truncated methods COFF')
    machine,count,_,symbol_at,symbol_count,optional,characteristics=struct.unpack_from('<HHIIIHH',raw)
    S.check(machine==0x8664 and count>0 and optional==0 and 20+count*40<=symbol_at and
        symbol_at+18*symbol_count+4<=len(raw),'Invalid AMD64 methods COFF header')
    strings=symbol_at+18*symbol_count;string_size=struct.unpack_from('<I',raw,strings)[0]
    S.check(string_size>=4 and strings+string_size==len(raw),'Invalid methods COFF string table')
    sections={};by_id={};allowed={'.text','.text$mn','.data','.bss','.rdata','.pdata','.xdata','.debug$S'}
    for ident in range(1,count+1):
        at=20+(ident-1)*40;name=raw[at:at+8].rstrip(b'\0').decode('ascii')
        virtual_size,virtual_address,size,data,reloc,line,nrel,nline,flags=struct.unpack_from('<IIIIIIHHI',raw,at+8)
        S.check(name in allowed and name not in sections and virtual_size==virtual_address==line==nline==0,
            'Unexpected methods COFF section/line metadata')
        S.check((name=='.bss' and data==0) or (size==0 and data==0) or 20+count*40<=data and data+size<=symbol_at,
            'Methods COFF section bytes escape their range')
        if flags&0x01000000:
            S.check(nrel==65535 and reloc+10<=symbol_at,'Invalid methods relocation overflow')
            total,si,kind=struct.unpack_from('<IIH',raw,reloc)
            S.check(total>65535 and si==kind==0,'Invalid methods relocation sentinel');nrel=total-1;reloc+=10
        S.check(not nrel or 20+count*40<=reloc and reloc+10*nrel<=symbol_at,'Invalid methods relocation range')
        row=dict(name=name,size=size,data=data,reloc=reloc,nrel=nrel,flags=flags&~0x01000000)
        sections[name]=row;by_id[ident]=row
    primaries=bytearray(symbol_count);symbol_hash=hashlib.sha256();defined_symbols=0
    def symbol(index):
        S.check(index<symbol_count,'COFF relocation target is outside the actual symbol table')
        at=symbol_at+18*index;name=raw[at:at+8]
        if name[:4]==b'\0'*4:
            offset=struct.unpack_from('<I',name,4)[0];S.check(4<=offset<string_size,'Invalid methods COFF name offset')
            end=raw.find(b'\0',strings+offset,strings+string_size);S.check(end>=0,'Unterminated methods COFF name')
            name=raw[strings+offset:end]
        else:name=name.rstrip(b'\0')
        value,section,kind,storage,aux=struct.unpack_from('<IhHBB',raw,at+8)
        S.check(section<=count and index+aux<symbol_count,'Invalid methods COFF symbol record')
        return (name.decode('ascii'),value,by_id[section]['name'] if section>0 else section,kind,storage),aux
    index=0
    while index<symbol_count:
        row,aux=symbol(index);primaries[index]=1
        if row[4]!=103 and row[2]!='.debug$S':
            aux_bytes=raw[symbol_at+(index+1)*18:symbol_at+(index+1+aux)*18]
            symbol_hash.update(json.dumps((row,aux_bytes.hex()),separators=(',',':')).encode()+b'\n');defined_symbols+=1
        index+=aux+1
    result={}
    widths={1:8,2:4,3:4,4:4,5:4,6:4,7:4,8:4,9:4,10:2,11:4}
    for name,section in sections.items():
        if name=='.debug$S':continue
        data=raw[section['data']:section['data']+section['size']] if name!='.bss' else b''
        digest=hashlib.sha256();previous=-1
        for i in range(section['nrel']):
            offset,index,kind=struct.unpack_from('<IIH',raw,section['reloc']+10*i)
            S.check(index<symbol_count and primaries[index] and kind in widths and previous<=offset and
                offset+widths[kind]<=len(data),'Invalid/overlapping methods COFF relocation')
            row,_=symbol(index);S.check(row[4]!=103 and row[2]!='.debug$S','Execution relocation targets a filename/debug symbol')
            addend=data[offset:offset+widths[kind]].hex()
            digest.update(json.dumps((offset,kind,addend,row),separators=(',',':')).encode()+b'\n');previous=offset+widths[kind]
        result[name]=dict(size=section['size'],flags=section['flags'],raw_sha256=hashlib.sha256(data).hexdigest(),
                          relocations=section['nrel'],normalized_relocations_sha256=digest.hexdigest())
    S.check('.pdata' in result and '.xdata' in result and result['.pdata']['size']%12==0 and
        result['.pdata']['relocations']==result['.pdata']['size']//4,'Missing/incomplete methods native x64 unwind table')
    return dict(machine=machine,characteristics=characteristics,sections=result,
        nondebug_primary_symbols=defined_symbols,nondebug_symbols_sha256=symbol_hash.hexdigest())


def machine_contract(text,obj,assembler):
    output=S.ART/'normal-methods/COFF-checks'/uuid4().hex;output.mkdir(parents=True)
    asm,expected=output/'canonical.asm',output/'canonical.obj';asm.write_text(text,encoding='utf-8',newline='\n')
    with (output/'assembler.log').open('xb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(expected),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    left,right=normalized_coff(obj),normalized_coff(expected)
    S.check(left==right,'Actual methods code/data/section flags/symbols/relocations/unwind differ from canonical reassembly')
    digest=hashlib.sha256(json.dumps(left,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    S.write(output/'verification.json',dict(schema=1,verified=True,scope='complete_independently_reassembled_methods_nondebug_COFF',
        object=S.artifact(obj),canonical_assembly=S.artifact(asm),canonical_object=S.artifact(expected),
        assembler=S.artifact(assembler),normalized=left,normalized_sha256=digest,
        ignored_fields=['COFF_timestamp_and_physical_offsets','.file_auxiliary_filename','.debug$S']))
    return digest


def verify(path):
    path=Path(path).resolve();candidate=S.read(path)
    S.check(path.is_relative_to(S.ART) and candidate['family']=='source-normal-methods-candidate',
        'Expected isolated normal methods candidate')
    meta=contract(S.checked(candidate['metadata']['input_state']))
    S.check(candidate['metadata']==meta and S.artifact(KERNEL)==candidate['kernel'] and
        S.artifact(ROOT/'scripts/normal-methods-source.py')==candidate['model'] and
        S.artifact(Path(__file__))==candidate['tool'],'Normal methods source model or kernel changed')
    text,exports,imports=assembly(meta)
    S.check(S.checked(candidate['assembly']).read_text(encoding='utf-8')==text and
        A.coff_symbols(S.checked(candidate['object']),C.FOREIGN)==(exports,imports) and
        set(candidate['exports'])==exports and set(candidate['imports'])==imports,
        'Normal methods canonical ASM or actual COFF differs')
    S.check(S.artifact(Path(candidate['assembler']['path']))==candidate['assembler'],'Methods assembler changed')
    machine=machine_contract(text,S.checked(candidate['object']),Path(candidate['assembler']['path']))
    return dict(schema=1,verified=True,scope='original_Class_getDeclaredMethods0_metadata_source_frames_ASM_COFF_only',
        candidate=S.artifact(path),original_native_methods=1,method_records=len(meta['source']['records']),
        type_capacity=meta['source']['type_capacity'],original_Java_constructor_required=True,
        represented_class_initializer_executed=False,extra_Java_oop_roots=False,
        canonical_reassembly_all_nondebug_bytes_and_relocations_verified=True,normalized_COFF_sha256=machine,
        shared_provider_registered=False,runtime572_modified=False,linked=False,executed=False,game_started=False)


def build(state,assembler,output):
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh isolated methods output required')
    meta=contract(state);output.mkdir(parents=True)
    text,exports,imports=assembly(meta);asm,obj=output/'provider.asm',output/'provider.obj'
    asm.write_text(text,encoding='utf-8',newline='\n')
    with (output/'assembler.log').open('wb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    S.check(A.coff_symbols(obj,C.FOREIGN)==(exports,imports),'Actual methods COFF definitions/imports differ')
    path=output/'candidate.json'
    S.write(path,dict(schema=1,family='source-normal-methods-candidate',metadata=meta,
        kernel=S.artifact(KERNEL),model=S.artifact(ROOT/'scripts/normal-methods-source.py'),tool=S.artifact(Path(__file__)),
        assembler=S.artifact(assembler),assembly=S.artifact(asm),object=S.artifact(obj),exports=sorted(exports),imports=sorted(imports),
        shared_provider_registered=False,runtime572_modified=False,linked=False,executed=False,game_started=False))
    S.write(output/'verification.json',verify(path));return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--state',type=Path,required=True)
    parser.add_argument('--assembler',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=S.ART/'normal-methods/candidates'/uuid4().hex)
    args=parser.parse_args();print(build(args.state.resolve(),args.assembler.resolve(),args.output))
