"""Extract one unchanged verified Java API wrapper/body for a property fixture."""
import hashlib
import json
from pathlib import Path
import re
import zipfile


def extract(nio,meta,output,tools,N):
    S,A=N.S,N.A
    source_model=S.module('native_library_API_source_spans','batch-source.py')
    source=source_model.Sources()
    summary=S.read(S.checked(nio['source_batch']))
    closure=S.read(Path(nio['selection_directory'])/'closure.json')
    [wanted]=[m for m in meta['api_fixture_methods'] if m['owner']=='java/lang/System']
    ident,owner=wanted['method'],wanted['class_id']
    S.check(str(ident) not in closure['selected_methods'],'API delta must add an actually missing original method')
    [system]=[c for c in closure['selected_classes'] if c['class_id']==owner]
    [root]=[f for f in system['fields'] if f['index']==meta['props_index']]
    S.check(root['reference'] and root['initial_bits']==0 and root['name']=='props',
            'System.props must already belong to the source static root bank')
    key=f'classes/{owner:06}.json'
    found=None
    for shard in summary['shards']:
        with zipfile.ZipFile(shard['zip']['path']) as archive:
            if key not in archive.namelist():
                continue
            S.checked(shard['zip'])
            compiled=json.loads(archive.read(key))
            [method]=[m for m in compiled['methods'] if m['id']==ident]
            S.check(compiled['source_sha256']==wanted['class_sha256'] and method['assembly_emitted'] and
                    method['operand_verified'] and method['code_sha256']==wanted['code_sha256'],
                    'API delta must come from the unchanged verified source class and Code')
            unit=shard['units'][method['assembly_unit']]
            original=S.checked(unit['assembly'])
            wrapper,body=[source.function(original,f'boom_m{ident}'+suffix) for suffix in ('','_body')]
            tables=''.join(source.handler_table(original,i) for i in sorted(set(
                map(int,re.findall(r'\bboom_handlers(\d+)\b',wrapper+body)))))
            found=shard,unit,compiled,method,wrapper,body,tables
            break
    S.check(found is not None,'Original API assembly unit is missing')
    shard,unit,compiled,method,wrapper,body,tables=found
    ir=S.module('native_library_API_original_Code','verify-translation-ir.py')
    original=ir.Source(S.original_class(summary,meta['classes']['java/lang/System']))
    [declaration]=[m for m in original.methods if (m['name'],m['descriptor'])==(wanted['name'],wanted['descriptor'])]
    code=original.code(declaration)
    source_pcs=[row['pc'] for row in ir.stream(code['bytes'])]
    actual_pcs=list(map(int,re.findall(rf'(?m)^boom_m{ident}_body_L(\d+):',body)))
    S.check(hashlib.sha256(code['bytes']).hexdigest()==wanted['code_sha256'] and source_pcs==actual_pcs and
            (not code['handlers'] or tables),'Original API Code, instruction labels or handler data differs')
    # The original body, every branch, and every referenced original handler
    # table are copied without edits. Only imports and PUBLIC declarations wrap it.
    selected=tables+'\n.code\n'+wrapper+'\n'+body
    defined=set(re.findall(r'(?m)^\s*(boom_\w+)(?::|\s+(?:PROC|LABEL|QWORD|DWORD|WORD|BYTE)\b)',selected))
    calls=set(re.findall(r'(?m)^\s*(?:call|jmp)\s+(boom_\w+)',selected))
    imports=set(re.findall(r'\bboom_\w+\b',selected))-defined
    functions={f'boom_m{ident}',f'boom_m{ident}_body'}
    asm,obj=output/'source-properties-api.asm',output/'source-properties-api.obj'
    text='option casemap:none\n'+''.join(f'EXTERN {name}:{"PROC" if name in calls else "BYTE"}\n' for name in sorted(imports))
    text+=''.join('PUBLIC '+name+'\n' for name in sorted(functions))+selected+'\nEND\n'
    asm.write_text(text)
    N.run([tools/'ml64.exe','/nologo','/c','/Fo'+str(obj),asm],output,'source-properties-api.log')
    S.check(A.coff_symbols(obj)==(functions,imports),'Actual API delta COFF changed its original function contract')
    proof=dict(original_method=wanted,source_class=meta['classes']['java/lang/System']['origin'],
        extractor_tool=S.artifact(Path(__file__)),
        original_shard=S.artifact(S.checked(shard['zip'])),original_assembly=unit['assembly'],
        original_COFF=unit['object'],generated_assembly=S.artifact(asm),generated_COFF=S.artifact(obj),
        original_wrapper_sha256=hashlib.sha256(wrapper.encode()).hexdigest(),
        original_body_sha256=hashlib.sha256(body.encode()).hexdigest(),
        original_handlers_sha256=hashlib.sha256(tables.encode()).hexdigest(),
        source_Code_handler_count=len(code['handlers']),source_bytecode_PCs=source_pcs,
        imported_symbols=sorted(imports),all_original_branches_retained=True,new_static_or_class_roots=False,
        existing_System_props_root=root,source_Java_codegen_rerun=False,original_input_modified=False,
        fixture_scope='original Properties APIs with non-null System.setProperties; not VM Phase1 startup')
    S.write(output/'source-properties-api.json',proof)
    return obj,S.artifact(output/'source-properties-api.json')
