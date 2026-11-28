"""Public instance-reference Lambda source and generated classfile API.

Original REF6 plans delegate unchanged. REF5/9 public own-declared methods use
the original receiver-inclusive MethodHandle shape and normal Java virtual or
interface bytecodes. Special/constructor handles, nonpublic access, boxing and
primitive arguments remain deferred. No runtime/MASM implementation is implied.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('instance_reference_original_source',ROOT/'scripts/normal-lambda-source.py')
C=importlib.util.module_from_spec(spec);sys.modules[spec.name]=C;spec.loader.exec_module(C)
S,I,P=C.S,C.I,C.P
require,reference,handle,method_type,source_member=C.require,C.reference,C.handle,C.method_type,C.source_member
BOOTSTRAP,DESCRIPTOR,MARKER,Pool=C.BOOTSTRAP,C.DESCRIPTOR,C.MARKER,C.Pool
RULE='normal-lambda-public-instance-reference-v1'
POLICY=dict(original_static_rule_preserved=True,implementation_handle_kinds=[5,9],
    public_own_declared_targets_only=True,bound_and_unbound_receivers=True,reference_captures_and_parameters=True,
    receiver_subtype_adaptation=True,other_capture_types_exact=True,primitive_results_exact_or_discard_to_void=True,
    boxing=False,primitive_argument_adaptation=False,special_or_constructor_handles=False,
    factory_allocation='fresh_normal_object',nullable_capture_fields=True,
    bound_receiver_caller_precondition_not_eager_factory_check=True,
    CallerSensitive_targets=False,signature_polymorphic_targets=False,
    original_target_annotations_checked=True,ordinary_virtual_dispatch_only=True,
    original_Java_Code_modified=False,automatic_GC=False,dynamic_class_unloading=False)


def public_module_access(sources,host,target):
    snapshot=S.read(S.checked(sources.catalog['module_snapshot']))
    host_id,target_id=host['origin']['source_id'],target['origin']['source_id']
    caller_module=host_id.split(':',1)[1] if host_id.startswith('jdk:') else None
    target_module=target_id.split(':',1)[1] if target_id.startswith('jdk:') else None
    package=target['name'].rpartition('/')[0]
    if caller_module==target_module:
        mode='same_original_module_or_classpath_unnamed'
        export=None
    else:
        require(target_module is not None,'named_to_unnamed_module_access_deferred')
        if caller_module is not None:
            require(target_module in snapshot['graph']['resolved'][caller_module]['reads'],'original_module_read_edge_required')
        exports=snapshot['modules'][target_module]['descriptor']['exports']
        allowed=[e for e in exports if e['package']==package and (not e['targets'] or caller_module in e['targets'])]
        require(len(allowed)==1,'original_public_package_export_required')
        export=allowed[0];mode='original_readable_exported_package'
    return dict(mode=mode,caller_module=caller_module,target_module=target_module,package=package,
        export=export,original_module_snapshot=sources.catalog['module_snapshot'],
        fixed_original_source_loader_domain=True,custom_dynamic_loader_access_proved=False)


def reference_loader_constraints(sources,host,target,args,result):
    rows=[]
    for descriptor in args+([result] if reference(result) else []):
        left=sources.ty(host['origin']['loader'],descriptor)
        right=sources.ty(target['origin']['loader'],descriptor)
        require(left['id']==right['id'],'original_reference_loader_constraint_differs')
        rows.append(dict(descriptor=descriptor,host_type_id=left['id'],declaring_loader_type_id=right['id']))
    return rows


def ordinary_instance_target(sources,cls,member):
    # Resolve annotations from the same locked original Class bytes as the
    # declaration. A selected dispatch thunk cannot supply caller-binding or
    # signature-polymorphic adaptation for a newly generated invocation.
    if cls['origin']['source_id'].startswith('jdk:'):
        blob=S.original_class(sources.summary,cls)
    else:
        path=sources.archive_paths.get(cls['origin']['source_id'])
        require(path is not None,'locked_non_JDK_archive_required')
        with zipfile.ZipFile(path) as archive:blob=archive.read(cls['origin']['jar_entry'])
    require(hashlib.sha256(blob).hexdigest()==cls['origin']['sha256'],'original_target_Class_digest_changed')
    F=C.module('verify-batch-frames')
    owner,methods=F.original_methods(blob)
    matches=[m for m in methods if (m['name'],m['descriptor'])==(member['name'],member['descriptor'])]
    require(owner==cls['name'] and len(matches)==1 and matches[0]['access']==member['access'],
        'original_target_annotation_declaration_differs')
    decl=matches[0];annotations=sorted(decl['annotations'])
    require('Ljdk/internal/reflect/CallerSensitive;' not in annotations,
        'CallerSensitive_instance_dispatch_requires_caller_binding_deferred')
    polymorphic=('Ljava/lang/invoke/MethodHandle$PolymorphicSignature;' in annotations or
        (owner in ('java/lang/invoke/MethodHandle','java/lang/invoke/VarHandle') and
         decl['access']&0x180==0x180 and P.signature(decl['descriptor'])[0]==['[Ljava/lang/Object;']))
    require(not polymorphic,'signature_polymorphic_instance_dispatch_deferred')
    require(not member['name'].startswith('<'),'special_instance_invocation_deferred')
    return dict(annotations=annotations,CallerSensitive=False,signature_polymorphic=False,
        class_sha256=cls['origin']['sha256'],annotation_source='original_Class_RuntimeVisibleAnnotations',
        parser='verify-batch-frames.original_methods')


def site(sources,cls,constant):
    raw=sources.raw(cls)
    tag,(bootstrap,_)=raw.cp[constant]
    require(tag==18,'InvokeDynamic_constant_required')
    _,arguments=raw.bootstraps[bootstrap]
    require(len(arguments)==3,'standard_metafactory_three_constants_required')
    implementation=handle(raw,arguments[1])
    if implementation['reference_kind']==6:return C.site(sources,cls,constant)
    return instance_site(sources,cls,constant)


def instance_site(sources,cls,constant):
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
    require(implementation['reference_kind'] in (5,9),'public_virtual_or_interface_implementation_required')
    require((implementation['reference_kind']==9)==implementation['interface'],'instance_reference_kind_and_member_tag_differ')
    sam_args,sam_result=P.signature(sam);dynamic_args,dynamic_result=P.signature(dynamic)
    declared_args,target_result=P.signature(implementation['descriptor'])
    target_args=['L'+implementation['owner']+';']+declared_args
    require(len(sam_args)==len(dynamic_args) and len(captures)+len(dynamic_args)==len(target_args),'capture_SAM_target_arity')
    require(len(captures)<=15 and len(sam_args)<=15 and len(target_args)<=16,'normal_value_ABI_capacity')
    require(all(reference(v) for v in captures+sam_args+dynamic_args+target_args),'reference_parameters_only')
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
    require(not target_member['access']&8 and target_member['access']&1 and target_cls['access']&1,
        'public_original_declared_instance_target_required')
    ordinary_target=ordinary_instance_target(sources,target_cls,target_member)
    same_host=target_cls['id']==cls['id']
    same_package=target_cls['origin']['loader']==loader and target_cls['name'].rpartition('/')[0]==cls['name'].rpartition('/')[0]
    module_access=public_module_access(sources,cls,target_cls)
    loader_constraints=reference_loader_constraints(sources,cls,target_cls,target_args,target_result)
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
        invocation=dict(reference_kind=implementation['reference_kind'],opcode=0xb9 if implementation['reference_kind']==9 else 0xb6,
            receiver_source='capture0' if captures else 'SAM0',declared_arguments=declared_args,effective_arguments=target_args,
            declaring_owner_initialization_requested=False,direct_declared_Java_body_required=False),
        module_access=module_access,reference_loader_constraints=loader_constraints,
        ordinary_target=ordinary_target,
        access_proof='public_declared_instance_member_with_original_module_and_loader_identity',
        module_identity='inherited_from_original_host_not_generated_source_id',generated_is_original=False,
        original_Java_Code_modified=False,assembled=False,linked=False,executed=False,game_started=False)


def generated_class(plan):
    if plan['implementation']['reference_kind']==6:return C.generated_class(plan)
    p=Pool();this=p.cls(plan['generated_name']);parent=p.cls('java/lang/Object');interface=p.cls(plan['interface']['name']);code_name=p.utf('Code')
    def ref(code,op,index):code.extend(bytes([op])+struct.pack('>H',index))
    def load(code,index):code.extend([0x19,index])
    fields=[];refs=[]
    for i,ty in enumerate(plan['captures']):
        name='c'+str(i);fields.append((0x1012,p.utf(name),p.utf(ty)));refs.append(p.member(9,plan['generated_name'],name,ty))
    ctor_desc='('+''.join(plan['captures'])+')V'
    ctor=bytearray([0x2a]);ref(ctor,0xb7,p.member(10,'java/lang/Object','<init>','()V'))
    for i,field in enumerate(refs):ctor.append(0x2a);load(ctor,i+1);ref(ctor,0xb5,field)
    ctor.append(0xb1)
    factory=bytearray();ref(factory,0xbb,this);factory.append(0x59)
    for i in range(len(refs)):load(factory,i)
    ref(factory,0xb7,p.member(10,plan['generated_name'],'<init>',ctor_desc));factory.append(0xb0)
    sam=bytearray()
    for field in refs:sam.append(0x2a);ref(sam,0xb4,field)
    for i,(erased,instantiated) in enumerate(zip(plan['sam_arguments'],plan['instantiated_arguments'])):
        load(sam,i+1)
        if erased!=instantiated:ref(sam,0xc0,p.cls(instantiated if instantiated.startswith('[') else instantiated[1:-1]))
    impl=plan['implementation']
    opcode=0xb9 if impl['reference_kind']==9 else 0xb6
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
