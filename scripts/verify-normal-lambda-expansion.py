"""Check derived lambda bytecode independently of the classfile writer."""
import argparse
import importlib.util
from pathlib import Path


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('normal_lambda_verifier_contract',ROOT/'scripts/normal-lambda-source.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
S=C.S


def code_steps(raw,method):
    result=[]
    for op in C.I.stream(raw.code(method)['bytes']):
        k=op['opcode']
        if k==0x2a:result.append(('load',0))
        elif k==0x19:result.append(('load',op['operand']['Local']))
        elif k in (0xbb,0xc0):result.append((k,raw.class_name(op['operand']['Constant'])))
        elif k in (0xb4,0xb5,0xb7,0xb8):
            member=raw.member(op['operand']['Constant'])
            result.append((k,member['owner'],member['name'],member['descriptor'],member.get('interface',False)))
        else:
            S.check(k in (0x59,0x57,0x58,0xb0,0xb1,0xac,0xad,0xae,0xaf),'Unexpected generated lambda bytecode')
            result.append((k,))
    return result


def class_semantics(record,contract):
    path=S.checked(record['class_file']);raw=C.I.Source(path.read_bytes());captures=contract['captures'];name=contract['generated_name']
    S.check(raw.name==name and raw.parent=='java/lang/Object' and raw.access==0x1030 and
        raw.interfaces==[contract['interface']['name']] and raw.attrs==[], 'Derived lambda header/interface/attributes differ')
    S.check([{k:f[k] for k in ('name','descriptor','access','constant_value')} for f in raw.fields]==[
        dict(name='c'+str(i),descriptor=t,access=0x1012,constant_value=None) for i,t in enumerate(captures)],
        'Derived capture fields differ from the validated source site')
    constructor='('+''.join(captures)+')V'
    signatures=[('<init>',constructor,0x1002),('$capture',contract['factory_descriptor'],0x1009),
        (contract['sam_name'],contract['sam_descriptor'],0x1011)]
    S.check([(m['name'],m['descriptor'],m['access']) for m in raw.methods]==signatures,'Derived method inventory differs')
    ctor=[('load',0),(0xb7,'java/lang/Object','<init>','()V',False)]
    for i,t in enumerate(captures):ctor += [('load',0),('load',i+1),(0xb5,name,'c'+str(i),t,False)]
    ctor += [(0xb1,)]
    factory=[(0xbb,name),(0x59,)]+[('load',i) for i in range(len(captures))]+[(0xb7,name,'<init>',constructor,False),(0xb0,)]
    sam=[]
    for i,t in enumerate(captures):sam += [('load',0),(0xb4,name,'c'+str(i),t,False)]
    for i,(u,t) in enumerate(zip(contract['sam_arguments'],contract['instantiated_arguments'])):
        sam.append(('load',i+1))
        if u!=t:sam.append((0xc0,t if t.startswith('[') else t[1:-1]))
    impl=contract['implementation'];sam.append((0xb8,impl['owner'],impl['name'],impl['descriptor'],impl['interface']))
    target=contract['implementation_result'];dynamic=contract['instantiated_result']
    if dynamic=='V' and target!='V':sam.append((0x58 if target in ('J','D') else 0x57,))
    elif C.reference(dynamic) and target!=dynamic:sam.append((0xc0,dynamic if dynamic.startswith('[') else dynamic[1:-1]))
    result=contract['sam_result'];sam.append((0xb0 if C.reference(result) else {'V':0xb1,'J':0xad,'F':0xae,'D':0xaf}.get(result,0xac),))
    S.check([code_steps(raw,m) for m in raw.methods]==[ctor,factory,sam],
        'Generated lambda capture order, casts, original target, return adaptation or constructor changed')
    for expected,method in zip(record['methods'],raw.methods):
        body=raw.code(method)
        S.check(expected['code_sha256']==C.hashlib.sha256(body['bytes']).hexdigest() and expected['code_length']==len(body['bytes']),
            'Derived frame Code identity changed')
    return dict(methods=len(raw.methods),captured_references=len(captures),source_target=impl,
        independent_bytecode_semantics_verified=True)


def verify(manifest_file):
    m=S.read(manifest_file)
    S.check(m['scope']=='normal_lambda_sparse_expansion_source_and_generated_classfiles_only' and
        m['source_rule']==S.artifact(ROOT/'scripts/normal-lambda-source.py'),'Current normal lambda source rule differs')
    s=C.Sources(Path(m['base']['batch']),Path(m['base']['plan']))
    S.check(s.base==m['base'],'Lambda expansion belongs to another verified original batch')
    ranges=dict(classes=len(s.classes),types=s.summary['runtime_metadata']['type_capacity'],
        methods=sum(len(c['method_ids']) for c in s.classes),fields=s.summary['runtime_metadata']['field_capacity'])
    S.check(m['original_ranges']==ranges,'Original class/type/method/field ranges changed')
    next_field=ranges['fields'];proofs=[]
    with C.zipfile.ZipFile(S.checked(s.summary['class_literals']['index'])) as archive:
        mirrors={r['type_id']:r for line in archive.open('types.jsonl') if (r:=C.json.loads(line))}
    for i,g in enumerate(m['generated']):
        host=s.classes[g['contract']['host']['class_id']];contract=C.site(s,host,g['contract']['constant'])
        S.check(contract==g['contract'],'Source bootstrap/SAM/implementation/access contract changed')
        typ=ranges['types']+i;method=ranges['methods']+3*i;fields=g['layout']['fields']
        S.check(g['type_id']==g['class_id']==typ and [r['id'] for r in g['methods']]==list(range(method,method+3)) and
            [f['id'] for f in fields]==list(range(next_field,next_field+len(contract['captures']))),'Sparse appended IDs changed')
        S.check(g['layout']==dict(abi=2,payload_bytes=len(fields)*8,reference_prefix=len(fields),fields=[
            dict(id=next_field+n,index=n,name='c'+str(n),descriptor=t,offset=n*8,reference=True,storage_bytes=8)
            for n,t in enumerate(contract['captures'])]),'Derived normal GC/reference layout changed')
        next_field+=len(fields)
        original=mirrors[host['id']]
        S.check((g['class_mirror']['module'],g['class_mirror']['loader'])==(original['module'],original['loader']) and
            g['class_mirror']['flags']==((original['flags']&1)|2),'Derived Module/loader/hidden identity changed')
        origin=g['origin'];generated=origin['generated']
        S.check(g['runtime_class_name']==C.runtime_class_name(contract,typ) and '/' in g['runtime_class_name'],
            'Hidden Class name lost its VM-generated non-binary suffix')
        S.check(origin['source_id']=='boom:'+C.RULE and origin['source_id']!=host['origin']['source_id'] and
            origin['loader']==host['origin']['loader'] and origin['sha256']==S.digest(S.checked(g['class_file']))['sha256'] and
            generated['host_sha256']==host['origin']['sha256'] and generated['host_Code_sha256']==contract['source_instruction']['code_sha256'] and
            generated['site']==contract['constant'] and generated['pc']==contract['source_instruction']['pc'],
            'Generated class provenance pretends to be original input or lost its source site')
        proofs.append(class_semantics(g,contract))
    S.check(m['appended_ranges']==dict(types=[ranges['types'],ranges['types']+len(proofs)],
        methods=[ranges['methods'],ranges['methods']+3*len(proofs)],fields=[ranges['fields'],next_field]),'Appended ranges differ')
    return dict(schema=1,verified=True,scope='derived_normal_lambda_source_and_classfile_semantics_only',
        expansion=S.artifact(manifest_file),generated_classes=len(proofs),classes=proofs,
        original_IDs_and_Java_Code_preserved=True,generated_classes_are_original_input=False,
        runtime_metadata_dispatch_Class_names_frames_extension_complete=False,linked=False,executed=False,game_started=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('manifest',type=Path);args=parser.parse_args()
    proof=verify(args.manifest.resolve());file=args.manifest.with_name('source-verification.json');S.write(file,proof);print(file)
