"""Prepare original Java file initialization tests after independent image proof."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('file_bootstrap_original_test_io',ROOT/'scripts/runtime-provider-source.py')
S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)


def prepare(directory,accepted_sha256,output,verify_class_monitor=False):
    directory,output=Path(directory).resolve(),Path(output).resolve()
    S.check(directory.is_relative_to(S.ART) and output.is_relative_to(S.ART) and not output.exists(),'Use accepted project evidence and a fresh source test record')
    proof_path=directory/'selection-verification.json';proof=S.read(proof_path);closure=S.read(directory/'closure.json')
    S.check(S.digest(proof_path)['sha256']==accepted_sha256 and proof['verified'] and proof['diagnostic_only'] and not proof['source_closure_complete'],'Explicitly accepted file source proof differs')
    S.check(hashlib.sha256((directory/'initialization-closure.asm').read_text(encoding='utf-8').encode()).hexdigest()==proof['closure_assembly_sha256'],'Accepted original file Java assembly changed')
    records=closure['runtime_provider_packs'];packs=[S.read(S.checked(p['manifest'])) for p in records]
    m=next(p for p in packs if p['family']=='normal-file-bootstrap-v1')
    S.check(m['tool_sources']==S.tools_identity(),'Accepted file provider tools changed')
    meta_path=S.checked(m['file_bootstrap_metadata']);meta=S.read(meta_path);fd_id=meta['descriptor']['class_id']
    fd=next(c for c in m['owner_sources'] if c['id']==fd_id);std={}
    for name in ('in','out','err'):
        matches=[i for i,f in enumerate(fd['fields']) if (f['name'],f['descriptor'],f['access'])==(name,'Ljava/io/FileDescriptor;',0x19)]
        S.check(len(matches)==1,'Original standard descriptor root differs');std[name]=f'boom_s{fd_id}_{matches[0]}'
    utf=next(c for c in m['owner_sources'] if c['name']=='java/lang/StringUTF16');shifts={}
    for name in ('HI_BYTE_SHIFT','LO_BYTE_SHIFT'):
        matches=[i for i,f in enumerate(utf['fields']) if (f['name'],f['descriptor'],f['access'])==(name,'I',0x1a)]
        S.check(len(matches)==1,'Original UTF16 byte-shift field differs');shifts[name]=f"boom_s{utf['id']}_{matches[0]}"
    monitor_source=None
    if verify_class_monitor:
        flags=next(p for p in packs if p['family']=='class-flags-v1')
        reflection=next(c for c in flags['owner_sources'] if c['name']=='jdk/internal/reflect/Reflection')
        summary=S.read(Path(closure['batch'])/'summary.json')
        parser=S.module('file_monitor_original_methods','verify-batch-frames.py')
        owner,methods=parser.original_methods(S.original_class(summary,reflection))
        candidates=[(i,r) for i,r in zip(reflection['method_ids'],methods)
                    if (r['name'],r['descriptor'])==('registerFieldsToFilter','(Ljava/lang/Class;Ljava/util/Set;)V')]
        S.check(owner==reflection['name'] and len(candidates)==1,'Original Reflection monitor method differs')
        method,raw=candidates[0];selected=closure['selected_methods'].get(str(method))
        code_sha=hashlib.sha256(raw['code'][0]).hexdigest() if raw['code'] else None
        S.check(raw['access']==0x29 and code_sha is not None and selected is not None and
                selected['class_id']==reflection['id'] and selected['source_sha256']==reflection['origin']['sha256'] and
                selected['code_sha256']==code_sha,'Original synchronized Reflection method is not selected')
        envelope=S.module('file_monitor_expected_envelope','verify-normal-monitors.py').expected(method,reflection['id'])
        S.check(envelope in (directory/'initialization-closure.asm').read_text(encoding='utf-8'),
                'Cold file test requires the canonical normal Class monitor envelope')
        monitor_source=dict(class_id=reflection['id'],owner=reflection['name'],source_sha256=reflection['origin']['sha256'],
            method=method,name=raw['name'],descriptor=raw['descriptor'],access=raw['access'],code_sha256=code_sha,
            wrapper_sha256=hashlib.sha256(envelope.encode()).hexdigest())
    runtime=Path(S.read(directory/'diagnostic.json')['global_provider_identity']['runtime_dll'])
    paths=[directory/p for p in ('closure.json','selection-verification.json','initialization-closure.asm','initialization-closure.obj','diagnostic-stops.obj','diagnostic-image.dll')]
    paths.extend(Path(p) for p in closure['objects']);paths.extend((runtime,meta_path,ROOT/'tests/host/FileBootstrapSourceProbe.cs',
        Path(__file__),ROOT/'scripts/Test-FileBootstrapSource.ps1'))
    if monitor_source:paths.extend((ROOT/'scripts/verify-normal-monitors.py',Path(closure['batch'])/'summary.json'))
    for p in records:paths.extend((S.checked(p['manifest']),S.checked(p['verification'])))
    result=dict(schema=1,image=str(directory/'diagnostic-image.dll'),runtime=str(runtime),metadata=meta,
        roots=[r['class_id'] for r in closure['requested_class_roots']],native_symbols={str(m['operation']):f"boom_m{m['method']}" for m in m['methods']},
        owner_classes=sorted({m['class_id'] for m in m['methods']}),standard_roots=std,utf16_shifts=shifts,
        normal_Class_monitor_source=monitor_source,
        inputs=[S.artifact(p) for p in dict.fromkeys(paths)],full_VM_bootstrap=False,game_started=False)
    S.write(output,result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',type=Path,required=True);p.add_argument('--accepted-verification-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--verify-class-monitor',action='store_true')
    a=p.parse_args();prepare(a.directory,a.accepted_verification_sha256,a.output,a.verify_class_monitor);print(json.dumps(dict(source=str(a.output),game_started=False)))
