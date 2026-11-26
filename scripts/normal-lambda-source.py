"""Source contract for sparse, compiler-owned normal LambdaMetafactory expansion.

This module does not patch a batch or mark a structural candidate executed.
The rule is selected by bootstrap/signatures/access, never a caller method name.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import zipfile


ROOT=Path(__file__).resolve().parents[1]
BOOTSTRAP='java/lang/invoke/LambdaMetafactory'
DESCRIPTOR=('(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;'
    'Ljava/lang/invoke/MethodType;Ljava/lang/invoke/MethodHandle;Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/CallSite;')
RULE='normal-lambda-static-reference-v1'
MARKER='$$BoomNormalLambda$'
POLICY=dict(bootstrap='exact_standard_metafactory',implementation_handle_kinds=[6],reference_captures=True,
    reference_parameters=True,instantiated_reference_casts=True,exact_primitive_results=True,reference_results=True,
    discard_implementation_result_for_void=True,boxing=False,primitive_parameter_adaptation=False,
    alternate_metafactory=False,serialization=False,bridge_methods=False,
    factory_allocation='fresh_normal_object_per_capture',original_Java_Code_modified=False,
    generated_class_kind='hidden',hidden_name_suffix='slash_0x_sparse_type_identity',
    generated_origin_is_original_JDK=False,sparse_types_after_original_type_capacity=True,
    original_class_array_primitive_method_and_field_IDs_preserved=True,
    generated_module_and_loader_inherited_from_host=True,shared_CP_multiple_instructions_supported=False,
    bootstrap_class_initialization_required=True,implementation_initialization_at_SAM_invocation=True,
    automatic_GC=False,dynamic_class_unloading=False,game_started=False)


def module(name):
    spec=importlib.util.spec_from_file_location('normal_lambda_'+name,ROOT/'scripts'/(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


S=module('runtime-provider-source');I=module('verify-translation-ir');P=module('plan-protocol-expansion')


class Deferred(ValueError):pass


def require(value,reason):
    if not value:raise Deferred(reason)


def reference(value):return value.startswith(('L','['))


def runtime_class_name(contract,type_id):
    # The nominal classfile name is independent of the VM's non-binary hidden
    # Class name. No JVM address or preexisting JDK class identity is copied.
    return contract['generated_name'].replace('/','.')+'/0x'+format(type_id,'016x')


def symbol_name(raw,index):
    tag,name=raw.cp[index];require(tag==7,'source_class_constant_required');return raw.text(name)


def handle(raw,index):
    tag,(kind,member)=raw.cp[index];require(tag==15,'source_direct_handle_required')
    target=raw.member(member);return dict(reference_kind=kind,**target)


def method_type(raw,index):
    tag,name=raw.cp[index];require(tag==16,'source_method_type_required');return raw.text(name)


class Sources:
    def __init__(self,batch,plan,lock=None):
        self.base,self.summary,self.classes=S.base(batch,plan)
        self.names={(c['origin']['loader'],c['name']):c for c in self.classes}
        self.catalog=S.read(S.checked(self.summary['frames']['original_system_catalog']))
        self.lock=S.read(lock) if lock else None;self.parsed={}
        self.archive_records=self.summary['frames'].get('original_input_files',{})
        self.archive_paths={name:Path(record['path']) for name,record in self.archive_records.items()}
        if self.lock:
            files=self.lock['files']
            self.archive_paths={r['id']:Path(r['path']) for r in files} if isinstance(files,list) else {
                key:Path(value['path']) for key,value in files.items()}
        with zipfile.ZipFile(S.checked(self.summary['runtime_metadata']['index'])) as archive:
            self.types={r['id']:r for line in archive.open('types.jsonl') if (r:=json.loads(line))}
        self.type_names={(r['defining_loader'],r['name']):r for r in self.types.values()}
        self.packages=self.catalog['packages']

    def lookup(self,loader,name):
        package=name.rpartition('/')[0]
        if package in self.packages:return self.names.get((self.packages[package]['loader'],name))
        order=['bootstrap']+(['platform'] if loader!='bootstrap' else [])
        if loader not in order:order.append(loader)
        return next((self.names[key,name] for key in order if (key,name) in self.names),None)

    def raw(self,cls):
        ident=cls['id']
        if ident not in self.parsed:
            if cls['origin']['source_id'].startswith('jdk:'):blob=S.original_class(self.summary,cls)
            else:
                path=self.archive_paths.get(cls['origin']['source_id'])
                require(path is not None,'locked_non_JDK_archive_required')
                record=self.archive_records.get(cls['origin']['source_id'])
                if record:
                    actual=S.digest(path)
                    require(all(actual[k]==record['digest'][k] for k in ('size','sha256')),'locked_archive_digest_changed')
                with zipfile.ZipFile(path) as archive:blob=archive.read(cls['origin']['jar_entry'])
            require(hashlib.sha256(blob).hexdigest()==cls['origin']['sha256'],'original_class_digest_changed')
            raw=I.Source(blob)
            require(raw.name==cls['name'] and len(raw.methods)==len(cls['method_ids']),'original_class_inventory_changed')
            self.parsed[ident]=raw
        return self.parsed[ident]

    def ty(self,loader,descriptor):
        require(reference(descriptor),'reference_type_required')
        if descriptor.startswith('L'):
            cls=self.lookup(loader,descriptor[1:-1]);require(cls is not None,'missing_reference_class')
            row=self.types.get(cls['id'])
        else:
            component=descriptor.lstrip('[')
            owner=self.lookup(loader,component[1:-1]) if component.startswith('L') else None
            defining=owner['origin']['loader'] if owner else 'bootstrap'
            row=self.type_names.get((defining,descriptor))
        require(row is not None,'missing_normal_reference_type');return row

    def assignable(self,loader,source,target):
        if source==target:return True
        a,b=self.ty(loader,source),self.ty(loader,target)
        if a['kind']==3:
            if b['name'] in ('java/lang/Object','java/lang/Cloneable','java/io/Serializable'):return True
            if b['kind']!=3:return False
            require(False,'array_covariance_adaptation_deferred')
        return b['id']==a['id'] or b['id'] in a['ancestors']


def source_member(sources,cls,name,descriptor):
    raw=sources.raw(cls)
    rows=[(ident,m) for ident,m in zip(cls['method_ids'],raw.methods) if (m['name'],m['descriptor'])==(name,descriptor)]
    require(len(rows)==1,'exact_declared_source_method_required')
    ident,method=rows[0];body=raw.code(method)
    return dict(method=ident,class_id=cls['id'],loader=cls['origin']['loader'],source_id=cls['origin']['source_id'],
        class_sha256=cls['origin']['sha256'],owner=cls['name'],name=name,descriptor=descriptor,access=method['access'],
        code_sha256=hashlib.sha256(body['bytes']).hexdigest() if body else None)


def site(sources,cls,constant):
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
    require(target_cls['origin']['source_id']==cls['origin']['source_id'],'cross_module_access_contract_deferred')
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
        access_proof='same_original_lookup_host' if same_host else 'same_locked_module_ordinary_member_access',
        module_identity='inherited_from_original_host_not_generated_source_id',generated_is_original=False,
        original_Java_Code_modified=False,assembled=False,linked=False,executed=False,game_started=False)


class Pool:
    def __init__(self):self.entries=[];self.class_names={}
    def push(self,raw):self.entries.append(raw);return len(self.entries)
    def utf(self,value):
        raw=value.encode('ascii');S.check(len(raw)<=65535,'Generated UTF8 overflow');return self.push(b'\x01'+struct.pack('>H',len(raw))+raw)
    def cls(self,value):
        # A hidden class's self references must share this_class's CP Class
        # entry. A second nominal Class entry would try ordinary name lookup,
        # which cannot discover a hidden class.
        if value not in self.class_names:self.class_names[value]=self.push(b'\x07'+struct.pack('>H',self.utf(value)))
        return self.class_names[value]
    def member(self,tag,owner,name,descriptor):
        o=self.cls(owner);n=self.utf(name);d=self.utf(descriptor);nt=self.push(b'\x0c'+struct.pack('>HH',n,d))
        return self.push(bytes([tag])+struct.pack('>HH',o,nt))


def generated_class(plan):
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
    impl=plan['implementation'];ref(sam,0xb8,p.member(11 if impl['interface'] else 10,impl['owner'],impl['name'],impl['descriptor']))
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
