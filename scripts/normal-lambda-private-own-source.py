"""Source API for a same-host private instance Lambda implementation.

site(sources, host, CP) checks the original Class/Code/bootstrap/annotations and
fixed original module/loader domain. A historical own-private REF7 is normalized
to REF5/invokevirtual182, while its private target is exact and non-overridable.
General super/interface special calls remain deferred. Public REF5/9 and static
plans delegate to their unchanged source APIs; existing generated prefix records
and policies are owned by the append caller and must not be reclassified here.

generated_class(plan) serializes the checked contract through the original
automatic Class backend. Captures may be references and exact boolean Z values;
SAM arguments remain references, with no boxing or primitive adaptation.
capture_layout preserves declaration/argument indexes and returns ABI2 offsets:
all oop slots form an eight-byte prefix, followed by individual boolean bytes.

The generated hidden nestmate access context is the actual original lookup
host, never inferred from a dollar name or fabricated NestHost attribute.
Original loader identities and Class hashes delimit this source proof; a class
transformation or loader replacement requires new eligibility/source proofs.
This API returns metadata/bytes and writes no outputs or runtime state. It
provides no custom-loader, unloading, GC execution or game-startup acceptance.
"""
import copy
import hashlib
import importlib.util
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parents[1]

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

INSTANCE=load('own_private_unchanged_public_instance_source',ROOT/'scripts/normal-lambda-instance-source.py')
STATIC=load('own_private_published_static_module_source',ROOT/'scripts/normal-lambda-static-module-source.py')
C,S,I,P=INSTANCE.C,INSTANCE.S,INSTANCE.I,INSTANCE.P
require,reference,handle,method_type,source_member=C.require,C.reference,C.handle,C.method_type,C.source_member
BOOTSTRAP,DESCRIPTOR,MARKER,Pool=C.BOOTSTRAP,C.DESCRIPTOR,C.MARKER,C.Pool
ordinary_instance_target=INSTANCE.ordinary_instance_target
public_module_access=INSTANCE.public_module_access
reference_loader_constraints=INSTANCE.reference_loader_constraints
RULE='normal-lambda-own-private-special-normalized-reference-z-v1'
POLICY=dict(schema='explicit-own-private-REF7-normalization-v1',
    original_handle_kind=7,normalized_invocation_kind=5,normalized_opcode=182,
    same_original_lookup_host_only=True,own_private_concrete_class_method_only=True,
    reference_captures_and_parameters=True,exact_boolean_captures=True,
    primitive_SAM_arguments=False,other_primitive_captures=False,boxing=False,
    hidden_nestmate_access_context='actual_original_lookup_host',
    private_method_non_overridable=True,public_instance_rule_relaxed=False,
    public_rules_delegated_unchanged=True,original_Java_Code_modified=False,
    original_handle_preserved_in_contract=True,native_admission_complete=False)

def _parameter_boundary(captures,sam,dynamic,target):
    require(all(reference(t) or t=='Z' for t in captures),'only_reference_or_exact_boolean_captures')
    require(all(reference(t) for t in sam+dynamic),'private_primitive_SAM_parameters_deferred')
    require(all(reference(t) or (i<len(captures) and t==captures[i]=='Z') for i,t in enumerate(target)),
        'primitive_target_arguments_must_be_exact_boolean_captures')

def _private_boundary(sources,host,target,member,interface):
    require(not host['origin'].get('generated') and not target['origin'].get('generated'),'original_lookup_host_required')
    require(not (host['access']|target['access'])&0x200,'private_interface_special_deferred')
    require(host['id']==target['id'] and host['name']==target['name'] and host['origin']==target['origin'],
        'REF7_non_own_or_super_special_deferred')
    require(member['class_id']==host['id'] and member['owner']==host['name'] and member['class_sha256']==host['origin']['sha256'],
        'exact_original_own_declaring_Class_required')
    require(member['access']&7==2 and not member['access']&(8|0x100|0x400) and member['code_sha256'],
        'own_private_concrete_nonstatic_Java_method_required')
    require(not member['name'].startswith('<'),'REF7_constructor_or_special_name_deferred')
    keys=sources.summary['class_literals']['loader_keys']
    require(host['origin']['loader'] in keys and interface['origin']['loader'] in keys,'original_fixed_loader_domain_required')
    require(interface['access']&1,'private_rule_public_SAM_interface_required')
    annotation=ordinary_instance_target(sources,target,member)
    return dict(mode='original_lookup_host_hidden_nestmate_own_private',lookup_host=copy.deepcopy(host),
        declaring_Class=copy.deepcopy(target['origin']),target_method=member['method'],
        hidden_nestmate=True,STRONG=True,raw_NestHost_invented=False,
        private_method_non_overridable=True,ordinary_target=annotation,
        interface_module_access=public_module_access(sources,host,interface))

def capture_layout(captures):
    """ABI2 compact-layout rule: references first, then exact byte booleans.

    Declaration/argument order is preserved by index, independently of physical
    offsets; no FieldUID, TypeUID or MethodUID is allocated here.
    """
    require(all(reference(t) or t=='Z' for t in captures),'capture_layout_type_deferred')
    order=sorted(range(len(captures)),key=lambda i:not reference(captures[i]))
    fields={};cursor=0
    for i in order:
        width=8 if reference(captures[i]) else 1
        cursor=(cursor+width-1)&~(width-1)
        fields[i]=dict(index=i,name='c'+str(i),descriptor=captures[i],offset=cursor,
            reference=reference(captures[i]),storage_bytes=width)
        cursor+=width
    return dict(abi=2,payload_bytes=cursor,reference_prefix=sum(reference(t) for t in captures),
        fields=[fields[i] for i in range(len(captures))],physical_field_order=order)

def private_site(sources,cls,constant):
    raw=sources.raw(cls);loader=cls['origin']['loader']
    require(not cls['origin'].get('generated'),'original_host_required')
    tag,(bootstrap,nt)=raw.cp[constant];require(tag==18,'InvokeDynamic_constant_required')
    tag,(name,descriptor)=raw.cp[nt];require(tag==12,'source_NameAndType_required')
    name,descriptor=raw.text(name),raw.text(descriptor)
    require(name not in ('$capture','<init>','<clinit>'),'reserved_generated_method_name_collision')
    target,args=raw.bootstraps[bootstrap];bsm=handle(raw,target)
    require((bsm['reference_kind'],bsm['owner'],bsm['name'],bsm['descriptor'],bsm['interface'])==
        (6,BOOTSTRAP,'metafactory',DESCRIPTOR,False),'exact_standard_metafactory_required')
    require(len(args)==3,'standard_metafactory_three_constants_required')
    captures,result=P.signature(descriptor)
    require(result.startswith('L'),'factory_must_return_interface')
    interface=sources.lookup(loader,result[1:-1]);require(interface is not None and interface['access']&0x200,'functional_interface_required')
    require(not interface['access']&0x2000 and not any(n=='PermittedSubclasses' for n,_ in sources.raw(interface).attrs),
        'annotation_or_sealed_functional_interface_deferred')
    require(interface['access']&1 or (interface['origin']['loader']==loader and interface['name'].rpartition('/')[0]==cls['name'].rpartition('/')[0]),
        'functional_interface_access_deferred')
    sam=method_type(raw,args[0]);dynamic=method_type(raw,args[2]);implementation=handle(raw,args[1])
    require(implementation['reference_kind']==7,'own_private_REF7_handle_required')
    require(not implementation['interface'],'private_interface_special_deferred')
    sam_args,sam_result=P.signature(sam);dynamic_args,dynamic_result=P.signature(dynamic)
    declared_args,target_result=P.signature(implementation['descriptor'])
    target_args=['L'+implementation['owner']+';']+declared_args
    require(len(sam_args)==len(dynamic_args) and len(captures)+len(dynamic_args)==len(target_args),'capture_SAM_target_arity')
    require(len(captures)<=15 and len(sam_args)<=15 and len(target_args)<=16,'normal_value_ABI_capacity')
    _parameter_boundary(captures,sam_args,dynamic_args,target_args)
    receiver=captures[0] if captures else dynamic_args[0]
    require(sources.assignable(loader,receiver,target_args[0]),'instance_receiver_subtype_required')
    require(captures[1:]==target_args[1:len(captures)] if captures else True,'exact_nonreceiver_capture_types_required')
    require(all(sources.assignable(loader,t,u) for u,t in zip(sam_args,dynamic_args)),'instantiated_argument_subtype_required')
    require(all(sources.assignable(loader,t,a) for t,a in zip(dynamic_args,target_args[len(captures):])),
        'instantiated_argument_must_widen_to_implementation')
    if reference(sam_result):
        require(reference(dynamic_result) and sources.assignable(loader,dynamic_result,sam_result),'instantiated_result_subtype_required')
        require(reference(target_result),'boxing_result_deferred')
    else:
        require(sam_result==dynamic_result,'primitive_result_adaptation_deferred')
        require(dynamic_result=='V' or target_result==dynamic_result,'primitive_result_exact_or_void_required')
    target_cls=sources.lookup(loader,implementation['owner']);require(target_cls is not None,'implementation_class_required')
    require(bool(target_cls['access']&0x200)==implementation['interface'],'implementation_reference_tag_differs')
    target_member=source_member(sources,target_cls,implementation['name'],implementation['descriptor'])
    private_access=_private_boundary(sources,cls,target_cls,target_member,interface)
    ordinary_target=ordinary_instance_target(sources,target_cls,target_member)
    same_host=target_cls['id']==cls['id']
    same_package=target_cls['origin']['loader']==loader and target_cls['name'].rpartition('/')[0]==cls['name'].rpartition('/')[0]
    module_access=public_module_access(sources,cls,target_cls)
    loader_constraints=reference_loader_constraints(sources,cls,target_cls,[t for t in target_args if reference(t)],target_result)
    bsm_cls=sources.lookup('bootstrap',BOOTSTRAP)
    require(bsm_cls is not None and bsm_cls['origin']['source_id']=='jdk:java.base' and not bsm_cls['origin'].get('generated'),
        'original_bootstrap_metafactory_class_required')
    bsm_member=source_member(sources,bsm_cls,'metafactory',DESCRIPTOR)
    require(bsm_member['access']&0x109==9 and bsm_member['code_sha256'],'original_concrete_bootstrap_required')
    ancestors={interface['id']}|set(sources.types[interface['id']]['ancestors']);abstract=set();initializers=[]
    for ident in sorted(ancestors):
        parent=sources.classes[ident]
        require(parent['name']!='java/io/Serializable','accidental_serialization_deferred')
        parsed=sources.raw(parent)
        for method in parsed.methods:
            if method['name']=='<clinit>':initializers.append(parent['id'])
            if method['access']&0x400 and not method['access']&8:
                abstract.add((method['name'],method['descriptor']))
    require(abstract=={(name,sam)},'single_exact_erased_SAM_required')
    require(not initializers,'SAM_interface_initializer_deferred')
    occurrences=[]
    for ident,method in zip(cls['method_ids'],raw.methods):
        body=raw.code(method)
        if body:
            for op in I.stream(body['bytes']):
                if op['opcode']==0xba and op['operand']['Constant']==constant:
                    occurrences.append(dict(method=ident,name=method['name'],descriptor=method['descriptor'],pc=op['pc'],
                        code_sha256=hashlib.sha256(body['bytes']).hexdigest()))
    require(len(occurrences)==1,'shared_constant_pool_entry_multiple_instructions_deferred')
    generated=cls['name']+MARKER+format(constant,'04x')
    require((loader,generated) not in sources.names,'generated_class_name_collision')
    require(all(ord(c)<128 for c in generated+descriptor+name+sam+dynamic+implementation['owner']+implementation['name']+implementation['descriptor']),
        'non_ASCII_class_member_descriptor_encoding_deferred')
    return dict(schema=1,rule=RULE,host=dict(class_id=cls['id'],name=cls['name'],origin=cls['origin']),constant=constant,
        source_instruction=occurrences[0],binding_label=f"boom_batch_call_{cls['id']}_{constant}_186",
        bootstrap=bsm,bootstrap_member=bsm_member,interface=dict(class_id=interface['id'],name=interface['name'],
            source_sha256=interface['origin']['sha256']),factory_descriptor=descriptor,captures=captures,
        sam_name=name,sam_descriptor=sam,sam_arguments=sam_args,sam_result=sam_result,
        instantiated_descriptor=dynamic,instantiated_arguments=dynamic_args,instantiated_result=dynamic_result,
        implementation=implementation,implementation_member=target_member,implementation_arguments=target_args,
        implementation_result=target_result,generated_name=generated,
        invocation=dict(reference_kind=implementation['reference_kind'],normalized_reference_kind=5,opcode=0xb6,
            receiver_source='capture0' if captures else 'SAM0',declared_arguments=declared_args,effective_arguments=target_args,
            declaring_owner_initialization_requested=False,direct_declared_Java_body_required=False,
            exact_original_normal_member_entry_required=True,virtual_override_selection_required=False),
        module_access=module_access,reference_loader_constraints=loader_constraints,
        ordinary_target=ordinary_target,
        access_proof='same_original_lookup_host_hidden_nestmate_private_non_overridable',
        private_access=private_access,normalized_invocation_kind=5,capture_layout=capture_layout(captures),
        module_identity='inherited_from_original_host_not_generated_source_id',generated_is_original=False,
        original_Java_Code_modified=False,assembled=False,linked=False,executed=False,game_started=False)


def _private_generated_class(plan):
    require(plan['implementation']['reference_kind']==7 and plan['normalized_invocation_kind']==5,'private_normalization_contract_required')
    p=Pool();this=p.cls(plan['generated_name']);parent=p.cls('java/lang/Object');interface=p.cls(plan['interface']['name']);code_name=p.utf('Code')
    def ref(code,op,index):code.extend(bytes([op])+struct.pack('>H',index))
    def load(code,index,descriptor):code.extend([0x19 if reference(descriptor) else 0x15,index])
    fields=[];refs=[]
    for i,ty in enumerate(plan['captures']):
        name='c'+str(i);fields.append((0x1012,p.utf(name),p.utf(ty)));refs.append(p.member(9,plan['generated_name'],name,ty))
    ctor_desc='('+''.join(plan['captures'])+')V'
    ctor=bytearray([0x2a]);ref(ctor,0xb7,p.member(10,'java/lang/Object','<init>','()V'))
    for i,field in enumerate(refs):ctor.append(0x2a);load(ctor,i+1,plan['captures'][i]);ref(ctor,0xb5,field)
    ctor.append(0xb1)
    factory=bytearray();ref(factory,0xbb,this);factory.append(0x59)
    for i in range(len(refs)):load(factory,i,plan['captures'][i])
    ref(factory,0xb7,p.member(10,plan['generated_name'],'<init>',ctor_desc));factory.append(0xb0)
    sam=bytearray()
    for field in refs:sam.append(0x2a);ref(sam,0xb4,field)
    for i,(erased,instantiated) in enumerate(zip(plan['sam_arguments'],plan['instantiated_arguments'])):
        load(sam,i+1,erased)
        if erased!=instantiated:ref(sam,0xc0,p.cls(instantiated if instantiated.startswith('[') else instantiated[1:-1]))
    impl=plan['implementation']
    opcode=0xb6  # Pinned JDK own-private REF7 normalization to REF5; never invokespecial183.
    ref(sam,opcode,p.member(11 if impl['interface'] else 10,impl['owner'],impl['name'],impl['descriptor']))
    if opcode==0xb9:sam.extend([1+len(P.signature(impl['descriptor'])[0]),0])
    result,desired=plan['implementation_result'],plan['instantiated_result']
    if desired=='V' and result!='V':sam.append(0x58 if result in ('J','D') else 0x57)
    elif reference(desired) and result!=desired:ref(sam,0xc0,p.cls(desired if desired.startswith('[') else desired[1:-1]))
    sam.append(0xb0 if reference(plan['sam_result']) else {'V':0xb1,'J':0xad,'F':0xae,'D':0xaf}.get(plan['sam_result'],0xac))
    methods=[(0x1002,p.utf('<init>'),p.utf(ctor_desc),len(refs)+1,ctor),
        (0x1009,p.utf('$capture'),p.utf(plan['factory_descriptor']),len(refs),factory),
        (0x1011,p.utf(plan['sam_name']),p.utf(plan['sam_descriptor']),len(plan['sam_arguments'])+1,sam)]
    blob=bytearray(b'\xca\xfe\xba\xbe\0\0\0A')+struct.pack('>H',len(p.entries)+1)+b''.join(p.entries)
    blob+=struct.pack('>6H',0x1030,this,parent,1,interface,len(fields))
    for flags,name,desc in fields:blob+=struct.pack('>4H',flags,name,desc,0)
    blob+=struct.pack('>H',len(methods))
    for flags,name,desc,locals_,code in methods:
        blob+=struct.pack('>5HIHHI',flags,name,desc,1,code_name,len(code)+12,64,locals_,len(code))+code+b'\0\0\0\0'
    blob+=b'\0\0';return bytes(blob)


def site(sources,cls,constant):
    raw=sources.raw(cls)
    tag,(bootstrap,_)=raw.cp[constant]
    require(tag==18,'InvokeDynamic_constant_required')
    _,arguments=raw.bootstraps[bootstrap]
    require(len(arguments)==3,'standard_metafactory_three_constants_required')
    implementation=handle(raw,arguments[1])
    kind=implementation['reference_kind']
    if kind==7:return private_site(sources,cls,constant)
    if kind==6:return STATIC.site(sources,cls,constant)
    return INSTANCE.site(sources,cls,constant)

def generated_class(plan):
    if plan['rule']==RULE:return _private_generated_class(plan)
    if plan['rule'] in (STATIC.RULE,C.RULE):return STATIC.generated_class(plan)
    return INSTANCE.generated_class(plan)
