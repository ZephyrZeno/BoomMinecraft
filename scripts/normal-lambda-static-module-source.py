"""Public static cross-source Lambda source and generated classfile API.

The original static rule remains unchanged for same-source sites. Cross-source
REF6 sites require public concrete Java declarations, original annotations,
JPMS reads and exports, and fixed original loader-identity constraints.
The generated Class delegates to the original Java member. No runtime, assembly
execution, automatic collection or game-startup acceptance is implied.
"""
import copy
import hashlib
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def _load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

C=_load('public_static_original_source',ROOT/'scripts/normal-lambda-source.py')
INSTANCE=_load('public_static_existing_module_annotation_predicates',ROOT/'scripts/normal-lambda-instance-source.py')
require,reference,handle,method_type,source_member=C.require,C.reference,C.handle,C.method_type,C.source_member
BOOTSTRAP,DESCRIPTOR,MARKER=C.BOOTSTRAP,C.DESCRIPTOR,C.MARKER
S,I,P=C.S,C.I,C.P
RULE='normal-lambda-public-static-module-reference-v2'
POLICY=copy.deepcopy(C.POLICY)
POLICY.update(cross_source_public_concrete_static_targets=True,
    cross_source_CallerSensitive_targets=False,cross_source_signature_polymorphic_targets=False,
    original_readable_exported_packages_only=True,original_loader_constraints_required=True,
    same_source_rule_delegated_unchanged=True,new_rule_prefix_policy_compatibility_proved=False)

def _public_static_boundary(sources,host,target,member,args,result,interface):
    require(host['origin']['source_id']!=target['origin']['source_id'],'cross_source_boundary_required')
    require(not target['origin'].get('generated') and not host['origin'].get('generated'),
        'original_host_and_target_required')
    require(target['access']&1 and member['access']&9==9 and not member['access']&0x500
        and member['code_sha256'],'public_concrete_declared_static_Java_target_required')
    require(interface['access']&1,'public_functional_interface_required_for_cross_source_rule')
    loader_keys=sources.summary['class_literals']['loader_keys']
    require(host['origin']['loader'] in loader_keys and target['origin']['loader'] in loader_keys
        and interface['origin']['loader'] in loader_keys,'original_fixed_loader_domain_required')
    # This reused predicate checks the exact original declaration and annotations;
    # it does not assume nonstatic access. The static access test is above.
    ordinary=INSTANCE.ordinary_instance_target(sources,target,member)
    module_access=INSTANCE.public_module_access(sources,host,target)
    interface_access=INSTANCE.public_module_access(sources,host,interface)
    constraints=INSTANCE.reference_loader_constraints(sources,host,target,args,result)
    return dict(target_module_access=module_access,interface_module_access=interface_access,
        reference_loader_constraints=constraints,ordinary_target=ordinary)

def _cross_source_static_site(sources,cls,constant):
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
    require(implementation['reference_kind']==6,'static_direct_implementation_required')
    sam_args,sam_result=P.signature(sam);dynamic_args,dynamic_result=P.signature(dynamic)
    target_args,target_result=P.signature(implementation['descriptor'])
    require(len(sam_args)==len(dynamic_args) and len(captures)+len(dynamic_args)==len(target_args),'capture_SAM_target_arity')
    require(len(captures)<=15 and len(sam_args)<=15 and len(target_args)<=16,'normal_value_ABI_capacity')
    require(all(reference(v) for v in captures+sam_args+dynamic_args+target_args),'reference_parameters_only')
    require(captures==target_args[:len(captures)],'exact_static_capture_types_required')
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
    require(target_member['access']&8 and not target_member['access']&0x500 and target_member['code_sha256'],
        'concrete_original_static_Java_target_required')
    same_host=target_cls['id']==cls['id']
    same_package=target_cls['origin']['loader']==loader and target_cls['name'].rpartition('/')[0]==cls['name'].rpartition('/')[0]
    require(same_host or not target_member['access']&2,'private_target_requires_same_original_lookup_host')
    require(target_member['access']&1 or same_package,'nonpublic_target_access_deferred')
    require(target_cls['access']&1 or same_package,'nonpublic_implementation_class_access_deferred')
    boundary=_public_static_boundary(sources,cls,target_cls,target_member,target_args,target_result,interface)
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
        access_proof='public_static_readable_exported_original_module_and_loader_identity',
        module_access=boundary['target_module_access'],functional_interface_module_access=boundary['interface_module_access'],
        reference_loader_constraints=boundary['reference_loader_constraints'],ordinary_target=boundary['ordinary_target'],
        original_static_site_boundary='cross_source_public_static_only',
        module_identity='inherited_from_original_host_not_generated_source_id',generated_is_original=False,
        original_Java_Code_modified=False,assembled=False,linked=False,executed=False,game_started=False)

def site(sources,cls,constant):
    raw=sources.raw(cls)
    tag,value=raw.cp[constant]
    require(tag==18,'InvokeDynamic_constant_required')
    bootstrap,_=value
    _,arguments=raw.bootstraps[bootstrap]
    require(len(arguments)==3,'standard_metafactory_three_constants_required')
    implementation=handle(raw,arguments[1])
    if implementation['reference_kind']!=6:
        return C.site(sources,cls,constant)
    target=sources.lookup(cls['origin']['loader'],implementation['owner'])
    require(target is not None,'implementation_class_required')
    if target['origin']['source_id']==cls['origin']['source_id']:
        return C.site(sources,cls,constant)
    return _cross_source_static_site(sources,cls,constant)

# The original automatic classfile/backend logic owns the return-Z bytecode.
# No Class is generated during this candidate preparation.
generated_class=C.generated_class
runtime_class_name=C.runtime_class_name
