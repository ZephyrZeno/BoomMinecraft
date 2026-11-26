"""Derive one normal JCLS unit. All Java and earlier UFMP artifacts retain their exact source records."""
import argparse
import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import tempfile
from copy import deepcopy
from pathlib import Path
import zipfile


def module(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


A=module('verify-batch-assembly')
B=module('boot-unnamed-normal-candidate')
S=B.S
ART=S.ART
DERIVATION='boot-unnamed-derivation.json'


def artifact(path):
    path=Path(path).resolve()
    return dict(path=str(path),digest=A.file_digest(path))


def record_key(record):
    digest=record['digest']
    return record['path'],digest['size'],digest['sha256'],digest.get('sha1')


def retained_records(node):
    result=set()
    if isinstance(node,dict):
        if 'path' in node and isinstance(node.get('digest'),dict):
            result.add(record_key(node))
        else:
            for item in node.values():result.update(retained_records(item))
    elif isinstance(node,list):
        for item in node:result.update(retained_records(item))
    return result


def coff_procedures(path):
    """Check all instruction/unwind bytes plus the complete relocations of those sections."""
    data=path.read_bytes()
    machine,nsec,_,_,_,opt,_=struct.unpack_from('<HHIIIHH',data)
    S.check(machine==0x8664 and nsec and opt==0,'Expected normal Win64 COFF')
    result={}
    for i in range(nsec):
        at=20+i*40
        name=data[at:at+8].rstrip(b'\0').decode()
        if name.split('$')[0] not in ('.text','.pdata','.xdata'):continue
        size,raw,relocs,_,count,_,flags=struct.unpack_from('<IIIIHHI',data,at+16)
        if count==0xffff and flags&0x01000000:
            count=struct.unpack_from('<I',data,relocs)[0]
        S.check(raw+size<=len(data) and relocs+count*10<=len(data) and name not in result,
                'Unexpected COFF procedure or relocation range')
        result[name]=dict(bytes=size,sha256=hashlib.sha256(data[raw:raw+size]).hexdigest(),
                          relocations=count,relocations_sha256=hashlib.sha256(data[relocs:relocs+count*10]).hexdigest())
    S.check(any(name.split('$')[0]=='.text' and row['bytes'] for name,row in result.items()),
            'Missing normal Class entry points')
    return result


def physical_pool(path,jcls):
    """Locate JCLS data by COFF symbols, before PE relocation or a host heap bind."""
    data=path.read_bytes()
    machine,nsec,_,sym,nsyms,opt,_=struct.unpack_from('<HHIIIHH',data)
    S.check(machine==0x8664 and opt==0,'Expected an AMD64 metadata object')
    sections={}
    for i in range(1,nsec+1):
        at=20+(i-1)*40
        sections[i]=struct.unpack_from('<IIIIHHI',data,at+16)
    wanted={'boom_java_class_pool','boom_java_class_root_count','boom_java_class_module_loaders',
        'boom_java_class_records','boom_java_class_roots','boom_java_class_loader_roots','boom_java_class_module_roots',
        'boom_java_class_reverse','boom_java_class_name_roots'}
    symbols={}
    strings=sym+18*nsyms
    i=0
    while i<nsyms:
        at=sym+18*i
        name=data[at:at+8]
        value,section,_,_,aux=struct.unpack_from('<IhHBB',data,at+8)
        if name[:4]==bytes(4):
            start=strings+int.from_bytes(name[4:],'little')
            name=data[start:data.index(0,start)]
        name=name.rstrip(b'\0').decode()
        if name in wanted:
            S.check(section in sections and name not in symbols,'Ambiguous normal data symbol')
            symbols[name]=(section,value)
        i+=aux+1
    S.check(symbols.keys()==wanted,'Actual JCLS section/symbol inventory differs')
    ntypes,nload,nmods=jcls['type_capacity'],len(jcls['loader_keys']),len(jcls['modules'])
    pool_section,poff=symbols['boom_java_class_pool']
    size,ptr,*_=sections[pool_section]
    S.check(poff+144<=size and ptr and struct.unpack_from('<IIII',data,ptr+poff)==(0x4a434c53,1,0,ntypes)
            and struct.unpack_from('<IIII',data,ptr+poff+80)==(jcls['reverse_slots']-1,nload,nmods,1),
            'Physical Class pool header, loader count or module count differs')
    mutable=bytearray(data[ptr:ptr+size])
    mutable[poff+88:poff+92]=bytes(4)
    const,root=symbols['boom_java_class_root_count']
    loaders,loff=symbols['boom_java_class_module_loaders']
    records,roff=symbols['boom_java_class_records']
    size,ptr,relocs,_,relcount,_,flags=sections[const]
    expected_loaders=[r['loader'] for r in jcls['modules']]
    S.check(const==loaders==records and ptr and root+8==loff and (loff+4*nmods+7)&~7==roff
            and roff+ntypes*48<=size and struct.unpack_from('<Q',data,ptr+root)[0]==jcls['root_cells']
            and list(struct.unpack_from('<'+'I'*nmods,data,ptr+loff))==expected_loaders
            and not any(data[ptr+loff+4*nmods:ptr+roff]),'Physical root count or loader-key table differs')
    if relcount==65535 and flags&0x01000000:
        relcount=struct.unpack_from('<I',data,relocs)[0]-1
        relocs+=10
    normalized=hashlib.sha256()
    S.check(relocs+relcount*10<=len(data),'Truncated JCLS record relocations')
    for offset,symbol_index,kind in struct.iter_unpack('<IIH',data[relocs:relocs+relcount*10]):
        S.check(roff<=offset<size,'Unexpected Class loader-key or root count relocation')
        normalized.update(struct.pack('<IIH',offset-roff,symbol_index,kind))
    bss,zero=symbols['boom_java_class_roots']
    reverse=zero+jcls['root_cells']*8
    S.check(symbols['boom_java_class_loader_roots']==(bss,zero+ntypes*8) and
            symbols['boom_java_class_module_roots']==(bss,zero+(ntypes+nload)*8) and
            symbols['boom_java_class_reverse']==(bss,reverse) and symbols['boom_java_class_name_roots'][0]==bss and
            not sections[bss][1],'Physical roots do not form one contiguous BSS collection span')
    return dict(normalized_writable_bytes=hashlib.sha256(mutable).hexdigest(),
      original_record_and_name_data=hashlib.sha256(data[ptr+roff:ptr+size]).hexdigest(),
      original_record_and_name_relocations=normalized.hexdigest(),record_relocations=relcount,type_capacity=ntypes,
      reverse_and_following_BSS_bytes=sections[bss][0]-reverse,
      class_names_from_reverse=symbols['boom_java_class_name_roots'][1]-reverse)


def derive(parent,assembly,coff,delta):
    fresh=deepcopy(parent)
    jcls=fresh['class_literals']
    keys=jcls['modules']
    S.check('bootstrap_unnamed_module_slot' not in jcls and len(keys)<65536 and jcls['loader_keys'][0]=='bootstrap'
            and [r['id'] for r in keys]==list(range(len(keys))) and all((r['loader'],r['name'])!=(0,None) for r in keys),
            'Sparse refresh requires one missing boot unnamed key in a verified legacy JCLS')
    slot=len(keys)
    keys.append(dict(id=slot,name=None,loader=0))
    jcls['bootstrap_unnamed_module_slot']=slot
    jcls['root_cells']+=1
    [unit]=jcls['units']
    unit.update(assembly=assembly,object=coff,body_bytes=unit['body_bytes']+delta,assembler_cache=None)
    return fresh


def parent_inputs(parent,plan,summary_sha,verification_sha):
    S.check(parent.is_relative_to(ART) and plan.is_relative_to(ART) and not (parent/DERIVATION).exists(),
            'Expected distinct project-owned parent batch with a legacy JCLS')
    accepted=dict(summary=artifact(parent/'summary.json'),verification=artifact(parent/'verification.json'),
                  plan=artifact(plan/'summary.json'))
    S.check(accepted['summary']['digest']['sha256']==summary_sha and accepted['verification']['digest']['sha256']==verification_sha,
            'Unexpected parent batch summary or full receipt')
    base,receipt=S.read(parent/'summary.json'),S.read(parent/'verification.json')
    S.check(receipt.get('verified') is True and all(receipt[k]['verified'] for k in ('class_literals','frames','properties'))
            and base['input_fingerprint']==S.read(plan/'summary.json')['input_fingerprint'],'Verified normal parent required')
    implementation=module('verify-batch-assembly')
    provenance=module('closure-batch-artifacts').configure(implementation,parent,base,plan)
    image_home=Path(receipt.get('sparse_original_vm_image_home',{}).get('vm_image_home',str(parent))).resolve()
    S.check(Path(base['properties']['vm_profile']['java_home']).resolve()==image_home,'Inherited VM home differs from original image')
    return base,accepted,implementation.artifact,provenance,image_home


def check_source(batch,parent,plan,accepted,base,old_resolve,write=False,assembler=None):
    [old]=base['class_literals']['units']
    parent_asm=old_resolve(parent,old['assembly'],'class-literals')
    parent_obj=old_resolve(parent,old['object'],'class-literals')
    text=parent_asm.read_text(encoding='utf-8')
    rebuilt=B.pool_overlay(text,base['class_literals'])
    delta=len(rebuilt.encode())-len(text.encode())
    asm=batch/'class-literals'/'0000.asm'
    obj=asm.with_suffix('.obj')
    if write:
        S.check(S.digest(assembler)['sha256']==old['assembler_cache']['assembler_sha256'],'Original JCLS assembler required')
        asm.parent.mkdir(parents=True,exist_ok=False)
        with asm.open('w',encoding='utf-8',newline='\n') as f:f.write(rebuilt)
        with (batch/'jcls-assembler.log').open('wb') as log:
            subprocess.run([assembler,'/nologo','/c',f'/Fo{obj}',asm],stdout=log,stderr=subprocess.STDOUT,check=True)
    S.check(asm.read_text(encoding='utf-8')==rebuilt,'JCLS assembly differs beyond the verified four pool declarations')
    parent_code=coff_procedures(parent_obj)
    S.check(parent_code==coff_procedures(obj) and A.coff_symbols(parent_obj)==A.coff_symbols(obj),
            'JCLS instructions, code relocations, unwind info or ABI symbols changed')
    corrected=derive(base,artifact(asm),artifact(obj),delta)
    S.check(physical_pool(parent_obj,base['class_literals'])==physical_pool(obj,corrected['class_literals']),
            'Normal JCLS writable data, type record bytes/relocations, names or strong root span changed')
    if write:S.write(batch/'summary.json',corrected)
    S.check(corrected==S.read(batch/'summary.json'),'Changes outside the JCLS pool metadata are forbidden')
    index=base['class_literals']['index']
    with zipfile.ZipFile(old_resolve(parent,index,'class-literals')) as z, z.open('types.jsonl') as rows:
        h=hashlib.sha256()
        count=0
        for line in rows:
            h.update(line)
            count+=1
    S.check(count==base['class_literals']['provided_types'],'Original type rows differ')
    info=dict(schema=1,scope='one_JCLS_bootstrap_unnamed_GC_root',parent_batch=str(parent),plan=str(plan),
        accepted_parent=accepted,summary=artifact(batch/'summary.json'),input_fingerprint=base['input_fingerprint'],
        ir_identity=base['ir_identity'],original_jcls=dict(assembly=old['assembly'],object=old['object']),
        jcls=dict(assembly=artifact(asm),object=artifact(obj)),unchanged_class_literal_index=index,
        unchanged_type_rows=count,unchanged_type_rows_sha256=h.hexdigest(),unchanged_COFF_procedures=parent_code,
        source_Java_units_retained=sum(len(s['units']) for s in base['shards']),source_Java_units_regenerated=0,
        previous_module_count=len(base['class_literals']['modules']),appended=corrected['class_literals']['modules'][-1],
        source_Java_or_roots_executed=False,full_batch_reverified=False)
    if write:S.write(batch/DERIVATION,info)
    S.check(info==S.read(batch/DERIVATION),'JCLS source derivation receipt changed')
    return corrected,info


def source_contract(batch,summary,plan=None):
    batch=Path(batch).resolve()
    S.check(batch.is_relative_to(ART),'Unexpected sparse batch location')
    proof=S.read(batch/DERIVATION)
    parent=Path(proof['parent_batch']).resolve()
    recorded_plan=Path(proof['plan']).resolve()
    S.check((plan is None or Path(plan).resolve()==recorded_plan) and parent!=batch,'JCLS source roots or plan differ')
    given=proof['accepted_parent']
    base,accepted,previous,identity,home=parent_inputs(parent,recorded_plan,given['summary']['digest']['sha256'],
                                                       given['verification']['digest']['sha256'])
    reconstructed,proof=check_source(batch,parent,recorded_plan,accepted,base,previous)
    S.check(summary==reconstructed,'Selected JCLS batch summary differs from its derivation')
    retained=retained_records(base)
    added={record_key(proof['jcls'][k]) for k in ('assembly','object')}
    removed={record_key(proof['original_jcls'][k]) for k in ('assembly','object')}
    def resolve(root,record,subdirectory=''):
        S.check(Path(root).resolve()==batch,'Unexpected JCLS verification root')
        key=record_key(record)
        if key in added:
            p=Path(record['path']).resolve()
            S.check(subdirectory=='class-literals' and p.parent==batch/'class-literals' and artifact(p)==record,
                    'New JCLS input path or full digest differs')
            return p
        S.check(key in retained and key not in removed,'Artifact is not retained in the certified parent batch')
        return previous(parent,record,subdirectory)
    resolve.verified_original_vm_image_home=home
    scope=dict(scope='parent_verified_batch_plus_one_JCLS_unit',parent=accepted,derivation=artifact(batch/DERIVATION),
               summary=proof['summary'],vm_image_home=str(home))
    return resolve,scope,identity


def check_full_receipt(receipt,parent,scope):
    # The extra data root changes no method/type/COFF coverage or native proof.
    # Require every old validation result, including all false execution claims.
    expected={k:v for k,v in parent.items() if k!='sparse_original_vm_image_home'}
    expected['bootstrap_unnamed_derivation']=scope
    S.check(receipt==expected,'Full JCLS receipt differs from the complete verified parent coverage')


def verified_resolver(batch,summary,plan=None):
    batch=Path(batch).resolve()
    resolve,scope,parent=source_contract(batch,summary,plan)
    receipt=S.read(batch/'verification.json')
    S.check(receipt.get('verified') is True and receipt['class_literals']['verified'] and
            receipt.get('bootstrap_unnamed_derivation')==scope and receipt['properties']['verified'],
            'A full JCLS batch verification matching the derivation is required')
    check_full_receipt(receipt,S.read(scope['parent']['verification']['path']),scope)
    return resolve,dict(**scope,certified_parent_derivation=parent,full_verification=artifact(batch/'verification.json'),
                        JCLS_resolver_sha256=S.digest(Path(__file__))['sha256'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='action',required=True)
    make=commands.add_parser('build')
    make.add_argument('--base',type=Path,required=True)
    make.add_argument('--plan',type=Path,required=True)
    make.add_argument('--base-summary-sha256',required=True)
    make.add_argument('--base-verification-sha256',required=True)
    make.add_argument('--assembler',type=Path,required=True)
    pool=commands.add_parser('verify-pool')
    full=commands.add_parser('verify-full')
    full.add_argument('--ir',type=Path,required=True)
    for command in (make,pool,full):command.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    output=args.output.resolve()
    S.check(output.is_relative_to(ART),'Project-owned batch output required')
    if args.action=='build':
        base,plan=args.base.resolve(),args.plan.resolve()
        summary,accepted,old,_,_=parent_inputs(base,plan,args.base_summary_sha256,args.base_verification_sha256)
        output.mkdir(parents=True,exist_ok=False)
        check_source(output,base,plan,accepted,summary,old,True,args.assembler.resolve())
        print(output/'summary.json')
    elif args.action=='verify-pool':
        current=S.read(output/'summary.json')
        _,scope,_=source_contract(output,current)
        unit=current['class_literals']['units'][0]
        proof=physical_pool(Path(unit['object']['path']),current['class_literals'])
        result=dict(scope=scope,physical_COFF=proof,new_module_key=current['class_literals']['modules'][-1],
                    original_java_regenerated=False,full_verification_claimed=False)
        target=output/'jcls-coff-verification.json'
        if target.exists():S.check(S.read(target)==result,'Different JCLS physical verification exists')
        else:S.write(target,result)
        print(target)
    else:
        full_verifier=module('verify-batch-assembly')
        resolve,scope,_=source_contract(output,S.read(output/'summary.json'))
        full_verifier.artifact=resolve
        plan=Path(scope['parent']['plan']['path']).parent
        verified=full_verifier.verify(output,plan,args.ir.resolve())
        S.check(verified['verified'] and verified['class_literals']['verified'],'Full batch validation failed')
        verified['bootstrap_unnamed_derivation']=scope
        check_full_receipt(verified,S.read(scope['parent']['verification']['path']),scope)
        target=output/'verification.json'
        if target.exists():S.check(S.read(target)==verified,'Full verification receipt has changed')
        else:
            with tempfile.TemporaryDirectory(dir=output) as tmp:
                temp=Path(tmp)/target.name
                S.write(temp,verified)
                os.link(temp,target)
        print(target)
