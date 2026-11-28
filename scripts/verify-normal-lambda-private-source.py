"""Independent generated private-Lambda Class bytecode semantics API.

semantics(blob, checked_plan, optional_record) independently reconstructs capture
field/method inventories, typed reference/boolean local loads, cast order,
normalized own-private invokevirtual182 and return adaptation. Original handle7
and explicit private normalization evidence remain mandatory. It validates
recorded Code hashes when a record is provided; it does not generate Class
bytes, rewrite prefix policies or infer source/machine/runtime admission.

These pure bytecode checks are one part of source validation. Eligibility,
loader/module/host identity, namespace append and normal dependency proofs are
the caller's separate obligations. No files, VM state or native roots are written.
"""
import hashlib
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

X=load('independent_private_reference_source',ROOT/'scripts/normal-lambda-instance-source.py')
C,S=X.C,X.S

def steps(raw,method):
    result=[]
    for op in C.I.stream(raw.code(method)['bytes']):
        code=op['opcode']
        if code==0x2a:result.append(('load',0))
        elif code==0x19:result.append(('load',op['operand']['Local']))
        elif code==0x15:result.append(('iload',op['operand']['Local']))
        elif code in (0xbb,0xc0):result.append((code,raw.class_name(op['operand']['Constant'])))
        elif code in (0xb4,0xb5,0xb6,0xb7,0xb8,0xb9):
            operand=op['operand']['Interface'] if code==0xb9 else op['operand']['Constant']
            constant=operand['constant'] if code==0xb9 else operand
            member=raw.member(constant)
            count=operand['count'] if code==0xb9 else None
            result.append((code,member['owner'],member['name'],member['descriptor'],member.get('interface',False),count))
        else:
            S.check(code in (0x59,0x57,0x58,0xb0,0xb1,0xac,0xad,0xae,0xaf),'Unsupported generated instruction')
            result.append((code,))
    return result


def semantics(blob,plan,record=None):
    raw=C.I.Source(blob);name=plan['generated_name'];captures=plan['captures']
    S.check(plan['implementation']['reference_kind']==7 and plan['invocation']['normalized_reference_kind']==5
        and plan['invocation']['opcode']==182 and plan['private_access']['private_method_non_overridable'] is True,
        'Explicit own-private normalization proof required')
    S.check(all(C.reference(t) or t=='Z' for t in captures),'Independent primitive capture domain')
    typed=lambda i,t:('load' if C.reference(t) else 'iload',i)
    S.check(raw.name==name and raw.parent=='java/lang/Object' and raw.access==0x1030 and
        raw.interfaces==[plan['interface']['name']] and raw.attrs==[],'Generated class/interface identity differs')
    S.check([{k:f[k] for k in ('name','descriptor','access','constant_value')} for f in raw.fields]==[
        dict(name='c'+str(i),descriptor=t,access=0x1012,constant_value=None) for i,t in enumerate(captures)],'Capture field declaration order differs')
    ctor_desc='('+''.join(captures)+')V'
    S.check([(m['name'],m['descriptor'],m['access']) for m in raw.methods]==[
        ('<init>',ctor_desc,0x1002),('$capture',plan['factory_descriptor'],0x1009),
        (plan['sam_name'],plan['sam_descriptor'],0x1011)],'Generated three-method inventory differs')
    ctor=[('load',0),(0xb7,'java/lang/Object','<init>','()V',False,None)]
    for i,t in enumerate(captures):ctor += [('load',0),typed(i+1,t),(0xb5,name,'c'+str(i),t,False,None)]
    ctor += [(0xb1,)]
    factory=[(0xbb,name),(0x59,)]+[typed(i,t) for i,t in enumerate(captures)]+[(0xb7,name,'<init>',ctor_desc,False,None),(0xb0,)]
    sam=[]
    for i,t in enumerate(captures):sam += [('load',0),(0xb4,name,'c'+str(i),t,False,None)]
    for i,(erased,dynamic) in enumerate(zip(plan['sam_arguments'],plan['instantiated_arguments'])):
        sam.append(('load',i+1))
        if erased!=dynamic:sam.append((0xc0,dynamic if dynamic.startswith('[') else dynamic[1:-1]))
    impl=plan['implementation'];kind=impl['reference_kind']
    opcode=0xb6  # Independently checked normalization of this exact private-own domain.
    count=1+len(C.P.signature(impl['descriptor'])[0]) if opcode==0xb9 else None
    sam.append((opcode,impl['owner'],impl['name'],impl['descriptor'],impl['interface'],count))
    target,dynamic=plan['implementation_result'],plan['instantiated_result']
    if dynamic=='V' and target!='V':sam.append((0x58 if target in ('J','D') else 0x57,))
    elif C.reference(dynamic) and target!=dynamic:sam.append((0xc0,dynamic if dynamic.startswith('[') else dynamic[1:-1]))
    result=plan['sam_result'];sam.append((0xb0 if C.reference(result) else {'V':0xb1,'J':0xad,'F':0xae,'D':0xaf}.get(result,0xac),))
    S.check([steps(raw,m) for m in raw.methods]==[ctor,factory,sam],
        'Independent capture order/receiver/casts/invocation/member/count/return-adaptation semantics differ')
    if record:
        S.check(len(record['methods'])==len(raw.methods),'Recorded method count differs')
        for expected,method in zip(record['methods'],raw.methods):
            code=raw.code(method)['bytes']
            S.check(expected['code_length']==len(code) and expected['code_sha256']==hashlib.sha256(code).hexdigest(),
                'Recorded generated method Code differs')
    return dict(verified=True,captured_references=sum(C.reference(t) for t in captures),
        captured_booleans=sum(t=='Z' for t in captures),methods=3,implementation_kind=kind,normalized_invocation_kind=5,
        invocation_opcode=opcode,invokeinterface_argument_count=count,
        receiver_origin=plan.get('invocation',{}).get('receiver_source'),
        independent_bytecode_semantics=True,business_implementation_body_copied=False)
