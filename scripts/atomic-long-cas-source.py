"""Original AtomicLong.VMSupportsCS8 source contract, not a CAS implementation."""
import hashlib
import struct

OWNER='java/util/concurrent/atomic/AtomicLong'
POOL='boom_provider_atomic_long_cas_pool'
SERVICE='boom_provider_atomic_long_cas_service'
CONTROL=set()
FOREIGN=set()
KERNELS=['classes32.asm','frames.asm']
PINS={
    'AtomicLong.java':'f6bbca6ce50db11061946699bfef58e7cbbc2b8db88acfc6f0be5ed83f002f74',
    'AtomicLong.c':'18999f8db127ca5097835ef9f6187287455b2aba76ed1ea06eb6cbd3ac9c7839',
    'jvm.cpp':'84436b103fb7869e445bac95d2e82e9de9160c2da327a4cf54f4e84555150ad9',
    'vm_version_x86.hpp':'28ad989bd5af4054ea72cf9696b9c3f1b31c300d59824cde7f4abf62b771e57e',
    'vm_version_x86.cpp':'6110ebac9feb66d4cdf38c992d5f9f082e40bc8dc713e3b6ceabb98193f75347',
    'abstract_vm_version.hpp':'c54c71fe9ba2e128b8a0f04b2b965f059152a09358b486f08d0ca196ff5a36b9',
    'globalDefinitions_x86.hpp':'cbae012a4f570b4acd245db0fcfb9b31b0dc722d4ebc75f0471df133c77a35d3',
}
POLICY=dict(normal_context_bytes=32,CPUID_leaf0_maximum_checked=True,CPUID_leaf1_EDX_bit=8,
    physical_CMPXCHG8B_capability=True,CMPXCHG16B_or_ECX_bit13_used=False,constant_true=False,
    target_profile_requires_CX8=True,missing_CPUID_leaf1_or_CX8='unsupported_Context20_not_Java_false',
    native_method_only=True,Java_clinit_and_static_field_assignment_unchanged=True,
    normal_original_native_frame=True,nonvolatile_RBX_preserved=True,existing_pending_context_preserved=True,
    allocations=False,Java_oop_roots=False,foreign_imports=False,CPU_feature_override_profile_supported=False,
    HotSpot_x86_SUPPORTS_NATIVE_CX8_is_an_ISA_guarantee=True,
    original_Unsafe_or_AtomicLong_CAS_operations_implemented_by_this_provider=False,
    source_transform_chain='original_locked_no_transforms')


def index(summary,classes,S):
    I=S.module('atomic_long_original_class','verify-translation-ir.py')
    [owner]=[c for c in classes if c['name']==OWNER and c['origin']['loader']=='bootstrap']
    S.check(owner['origin']['source_id']=='jdk:java.base' and not owner['origin'].get('generated'),'Original bootstrap AtomicLong required')
    raw=S.original_class(summary,owner);source=I.Source(raw)
    S.check(struct.unpack_from('>H',raw,6)[0]==65 and source.name==OWNER and len(source.methods)==len(owner['method_ids']),
        'Original AtomicLong class version/name/inventory differs')
    methods=[];initializers=[]
    for ident,method in zip(owner['method_ids'],source.methods):
        code=source.code(method)
        if (method['name'],method['descriptor'])==('VMSupportsCS8','()Z'):
            S.check(method['access']==0x10a and code is None,'AtomicLong native flags or absent Code changed')
            methods.append(dict(method=ident,class_id=owner['id'],class_sha256=owner['origin']['sha256'],
                loader='bootstrap',source_id='jdk:java.base',owner=OWNER,name=method['name'],descriptor=method['descriptor'],
                access=method['access'],operation=0))
        if (method['name'],method['descriptor'])==('<clinit>','()V'):
            S.check(method['access']==8 and code is not None,'Original AtomicLong initializer Code required')
            instructions=list(I.stream(code['bytes']));pairs=[]
            for a,b in zip(instructions,instructions[1:]):
                if a['opcode']==0xb8 and b['opcode']==0xb3:
                    call=source.member(a['operand']['Constant']);field=source.member(b['operand']['Constant'])
                    if (call['owner'],call['name'],call['descriptor'])==(OWNER,'VMSupportsCS8','()Z'):
                        S.check(field==dict(owner=OWNER,name='VM_SUPPORTS_LONG_CAS',descriptor='Z'),'Original capability publication changed')
                        pairs.append(dict(native_call_pc=a['pc'],source_putstatic_pc=b['pc'],field=field))
            S.check(len(pairs)==1,'Original Java must call the native and publish its own result exactly once')
            initializers.append(dict(method=ident,owner=OWNER,name='<clinit>',descriptor='()V',access=method['access'],
                class_id=owner['id'],class_sha256=owner['origin']['sha256'],code_sha256=hashlib.sha256(code['bytes']).hexdigest(),
                publication=pairs[0]))
    fields=[(i,f) for i,f in enumerate(source.fields) if (f['name'],f['descriptor'],f['access'])==('VM_SUPPORTS_LONG_CAS','Z',0x18)]
    S.check(len(methods)==len(initializers)==len(fields)==1,'Original AtomicLong capability inventory incomplete')
    directory=S.ART/'atomic-long-cas/pinned-sources/jdk-21.0.13+3'
    pins={name:S.artifact(directory/name) for name in PINS}
    S.check(all(pins[n]['digest']['sha256']==h for n,h in PINS.items()),'Locked original AtomicLong/HotSpot source changed')
    return dict(schema=1,owner=owner['id'],methods=methods,original_java=initializers,
        capability_field=dict(declaring_class=owner['id'],declaring_field=fields[0][0],name='VM_SUPPORTS_LONG_CAS',descriptor='Z',
            source_access=0x18,symbol=f"boom_s{owner['id']}_{fields[0][0]}"),
        native_sources=pins,source_chain=['AtomicLong.c','JVM_SupportsCX8','Abstract_VM_Version::supports_cx8'],
        x86_runtime_feature_initialization='_supports_cx8 = supports_cmpxchg8() = CPUID.1.EDX[8]',
        x86_build_guarantee='globalDefinitions_x86.hpp SUPPORTS_NATIVE_CX8 makes the original getter true for that supported ISA',
        required_classes=[owner['id']],required_java_methods=[],required_base_modules=['runtime_metadata'],
        required_provider_families=[],native_root_spans=[],pool_bytes=16,pool_abi=1)


def native_imports(meta):
    [row]=meta['methods']
    return {'boom_class_ensure32','boom_trace_enter','boom_trace_leave'},\
        {'boom_trace_pool',f"boom_class{row['class_id']}",f"boom_trace_method{row['method']}"}


def data(meta):
    return f'.const\nALIGN 8\nPUBLIC {POOL}\n{POOL} DWORD 041434153h,1,0,0\n'
