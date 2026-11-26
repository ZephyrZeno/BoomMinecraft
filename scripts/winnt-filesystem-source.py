"""Verify the original WinNTFileSystem native and the normal java.io.File.path field."""
import json


OWNER = 'java/io/WinNTFileSystem'
POOL = 'boom_provider_winnt_file_pool'
SERVICE = 'boom_provider_winnt_file_service'
FOREIGN = {'GetModuleHandleExW', 'GetProcAddress', '__imp_CreateFileW'}
CONTROL = set()
KERNELS = ['classes32.asm', 'objects.asm', 'frames.asm']
POLICY = dict(original_File_class_initialization=True, source_FieldID_for_File_path=True,
              optional_final_path_function_from_Windows=True, native_filesystem_operations_implemented=False)


def index(summary, classes, S):
    names = {c['name']: c for c in classes if c['origin']['loader'] == 'bootstrap' and c['name'] in (OWNER, 'java/io/File')}
    owner, file = names[OWNER], names['java/io/File']
    S.check(owner['access'] == 0x30 and file['access'] == 0x21 and all(
        c['origin']['source_id'] == 'jdk:java.base' and not c['origin'].get('generated') for c in (owner,file)),
        'Original Windows filesystem source classes differ')
    R = S.module('winnt_source_reader','verify-batch-frames.py')
    name, methods = R.original_methods(S.original_class(summary,owner))
    matches = [(i,m) for i,m in zip(owner['method_ids'],methods) if (m['name'],m['descriptor']) == ('initIDs','()V')]
    S.check(name == OWNER and len(methods) == len(owner['method_ids']) and len(matches) == 1 and
            matches[0][1]['access'] == 0x10a and matches[0][1]['code'] is None, 'Original WinNTFileSystem.initIDs differs')
    member = dict(method=matches[0][0],class_id=owner['id'],class_sha256=owner['origin']['sha256'],loader='bootstrap',
                  source_id='jdk:java.base',owner=OWNER,name='initIDs',descriptor='()V',access=0x10a,operation=0)
    with S.checked(summary['layouts']).open(encoding='utf-8') as stream:
        layout = next((row for line in stream if (row := json.loads(line))['class_id'] == file['id']),None)
    S.check(layout is not None,'File normal layout is missing')
    F = S.module('winnt_file_fields','file-bootstrap-source.py')
    field = F.fields(file,layout,[('path','Ljava/lang/String;',0x12,8,True)],S)[0]
    field['index'] = next(i for i,f in enumerate(file['fields']) if (f['name'],f['descriptor']) == ('path','Ljava/lang/String;'))
    return dict(schema=1, owner=owner['id'], methods=[member], file_class=file['id'], file_sha256=file['origin']['sha256'],
                field=field, required_classes=[owner['id'],file['id']], pool_bytes=64, pool_abi=1,
                source_transform_chain='original_locked_no_transforms')


def native_imports(meta):
    return ({'GetModuleHandleExW','GetProcAddress','boom_trace_enter','boom_trace_leave'},
            {'__imp_CreateFileW','boom_trace_pool',f"boom_class{meta['file_class']}", f"boom_layout{meta['file_class']}",
             f"boom_trace_method{meta['methods'][0]['method']}"})


def data(meta):
    owner, field = meta['file_class'], meta['field']
    return (f'.const\nALIGN 8\nrpr_file_path_field QWORD OFFSET boom_layout{owner}\n'
            f" DWORD {field['offset']},{field['index']},{owner},8\n"
            'rpr_final_path_name BYTE "GetFinalPathNameByHandleW",0\n'
            f'.data\nALIGN 8\nPUBLIC {POOL}\n{POOL} DWORD 053464E57h,1,0,0\n'
            f' QWORD OFFSET boom_class{owner},OFFSET rpr_file_path_field,0,0,0,0\n')
