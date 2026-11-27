"""Prepare or consume a selection, assemble, LINK and run its full verifier."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def check(value,message):
    if not value:raise ValueError(message)

def artifact(path):
    path=Path(path).resolve();raw=path.read_bytes()
    return dict(path=str(path),digest=dict(size=len(raw),sha256=hashlib.sha256(raw).hexdigest()))

def module(root,file):
    spec=importlib.util.spec_from_file_location('diagnostic_build_'+file.replace('-','_'),Path(root)/'scripts'/file)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

def runtime_dll(value):
    path=Path(value).resolve();return path if path.suffix.lower()=='.dll' else path/'boom-runtime.dll'

def installed_msvc():
    root=Path(os.environ['ProgramFiles(x86)'])/'Microsoft Visual Studio/Installer/vswhere.exe'
    result=subprocess.run([str(root),'-latest','-products','*','-requires','Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath'],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    values=result.stdout.decode('utf-8-sig').splitlines();check(values and values[0].strip(),'MSVC x64 tools were not found')
    install=Path(values[0].strip()).resolve();version=install/'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt'
    bin_path=install/'VC/Tools/MSVC'/version.read_text().strip()/'bin/Hostx64/x64'
    return bin_path/'ml64.exe',bin_path/'link.exe',[artifact(root),artifact(version)]

def build(root,batch,plan,directory,runtime,assembler=None,linker=None,*,prepared_selection=False,
          class_roots=(),entries=(),admit_profile=None,receiver_class=None,provider_packs=(),
          parallel_assembly=False,workers=8,code_mib=8):
    root,batch,plan,directory=map(lambda p:Path(p).resolve(),(root,batch,plan,directory))
    discovery=[]
    if assembler is None:
        assembler,discovered_linker,discovery=installed_msvc()
        if linker is None:linker=discovered_linker
    assembler=Path(assembler).resolve();linker=Path(linker).resolve() if linker is not None else assembler.with_name('link.exe')
    runtime=runtime_dll(runtime)
    check(directory.is_relative_to(root/'.boom'),'Diagnostic output must stay in project outputs')
    check(assembler.name.lower()=='ml64.exe' and linker.name.lower()=='link.exe','Expected x64 MASM and native LINK')
    check(1<=workers<=8 and 1<=code_mib<=1024,'Invalid diagnostic assembler budgets')
    check(not prepared_selection or not any((class_roots,entries,admit_profile,receiver_class,provider_packs)),
          'Prepared selection cannot add competing source roots or provider inputs')
    outputs=['diagnostic-image.dll','link.rsp','build.json','selection-verification.json','assembly-provenance.json']
    check(not any((directory/name).exists() for name in outputs),'Diagnostic build outputs are immutable; use a fresh selection')
    inputs=discovery+[artifact(p) for p in [__file__,assembler,linker,runtime,runtime.with_suffix('.lib'),runtime.with_name('runtime.json'),
        root/'scripts/prepare-diagnostic-closure.py',root/'scripts/diagnostic-objects.py',root/'scripts/parallel-diagnostic-assembly.py',
        root/'scripts/canonical-link-response.py',root/'scripts/run-diagnostic-verification.py',root/'scripts/verify-diagnostic-closure.py']]
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    if not prepared_selection:
        check(not directory.exists(),'Fresh selection output already exists');directory.mkdir(parents=True)
        command=[sys.executable,str(root/'scripts/prepare-diagnostic-closure.py'),str(batch),'--plan',str(plan),'--output',str(directory),'--runtime',str(runtime)]
        for value in class_roots:command+=['--class-root',value]
        for value in entries:command+=['--entry',value]
        for value in provider_packs:command+=['--provider-pack',str(Path(value).resolve())]
        if admit_profile is not None:command+=['--admit-profile',str(Path(admit_profile).resolve())]
        if receiver_class:command+=['--receiver-class',receiver_class]
        with (directory/'prepare.log').open('xb') as out,(directory/'prepare.err').open('xb') as err:
            result=subprocess.run(command,cwd=root,stdout=out,stderr=err,creationflags=flags)
        check(result.returncode==0,'Diagnostic source selection failed; prepare logs are preserved')
    check((directory/'closure.json').is_file(),'Prepared source selection is missing')
    closure=json.loads((directory/'closure.json').read_bytes())
    check(Path(closure['batch']).resolve()==batch and Path(closure['plan']).resolve()==plan,'Diagnostic source batch or plan differs')
    for name in ('closure.json','diagnostic.json','initialization-closure.asm','diagnostic-stops.asm'):inputs.append(artifact(directory/name))
    packs=closure['runtime_provider_packs'];selected=closure.get('selected_runtime_provider_packs',[])
    check(len(selected)==len(set(selected)) and all(type(i) is int and 0<=i<len(packs) for i in selected),'Invalid selected provider index list')
    families=[]
    for index in selected:
        reference=packs[index]['manifest'];check(artifact(reference['path'])==reference,'Selected provider manifest changed before link')
        inputs.append(reference);families.append(json.loads(Path(reference['path']).read_bytes())['family'])
    objects_tool=module(root,'diagnostic-objects.py')
    objects_tool.assemble(directory,assembler,parallel_assembly=parallel_assembly,workers=workers,code_mib=code_mib)
    sealed=objects_tool.verify(directory)
    objects=[unit['object']['path'] for unit in sealed['units']]+list(closure['objects'])
    check(len(objects)==len(set(str(Path(p).resolve()).casefold() for p in objects)),'Duplicate diagnostic object')
    link_tool=module(root,'canonical-link-response.py')
    libraries=link_tool.diagnostic_libraries(runtime,winsock='normal-native-libraries-v1' in families)[0]
    inputs.extend(artifact(path) for path in [*objects,*libraries])
    image=directory/'diagnostic-image.dll'
    tokens=[*link_tool.PREFIXES['diagnostic'],'/OUT:"'+str(image)+'"',*['"'+str(p)+'"' for p in [*objects,*libraries]],
            *['/EXPORT:'+symbol for symbol in sorted(set(closure['exports']))]]
    response=directory/'link.rsp';response.write_text('\n'.join(tokens)+'\n',encoding='utf-8')
    link_tool.verify(response,profile='diagnostic',output=image,objects=objects,library_choices=[libraries],exports=closure['exports'])
    with (directory/'link.log').open('xb') as log:
        result=subprocess.run([str(linker),'@'+str(response)],cwd=root,stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
    check(result.returncode==0,'Diagnostic image link failed; link.log is preserved')
    check([artifact(row['path']) for row in inputs]==inputs,'Diagnostic build input changed')
    runner=module(root,'run-diagnostic-verification.py')
    status=runner.verify(directory)
    check(status['state']=='verified' and status['exit_code']==0,'Independent full diagnostic verification failed; status/logs are preserved')
    proof=json.loads((directory/'selection-verification.json').read_bytes())
    check(proof['verified'] is True and proof['diagnostic_only'] is True and proof['source_closure_complete'] is False,'Diagnostic verifier returned an unexpected scope')
    check([artifact(row['path']) for row in inputs]==inputs,'Diagnostic input changed during full verification')
    record=dict(schema=1,scope='prepared_or_new_diagnostic_selection_assembly_link_full_source_verification',
        source_manifest=artifact(directory/'closure.json'),source_verification=artifact(directory/'selection-verification.json'),
        verification_status=artifact(directory/'selection-verification-status.json'),image=artifact(image),
        assembly_provenance=artifact(directory/'assembly-provenance.json'),link_response=artifact(response),
        inputs=inputs,selected_families=families,prepared_selection=prepared_selection,
        verified=True,full_source_verification_repeated=True,executed=False,game_started=False)
    (directory/'build.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    return image

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT)
    for name in ('batch','plan','output','runtime'):parser.add_argument('--'+name,type=Path,required=True)
    for name in ('assembler','linker'):parser.add_argument('--'+name,type=Path)
    parser.add_argument('--prepared-selection',action='store_true');parser.add_argument('--parallel-assembly',action='store_true')
    parser.add_argument('--workers',type=int,default=8);parser.add_argument('--code-mib',type=int,default=8)
    parser.add_argument('--class-root',action='append',default=[]);parser.add_argument('--entry',action='append',default=[])
    parser.add_argument('--admit-profile',type=Path);parser.add_argument('--receiver-class');parser.add_argument('--provider-pack',type=Path,action='append',default=[])
    args=parser.parse_args()
    print(build(args.root,args.batch,args.plan,args.output,args.runtime,args.assembler,args.linker,
        prepared_selection=args.prepared_selection,class_roots=args.class_root,entries=args.entry,admit_profile=args.admit_profile,
        receiver_class=args.receiver_class,provider_packs=args.provider_pack,parallel_assembly=args.parallel_assembly,workers=args.workers,code_mib=args.code_mib))

if __name__=='__main__':main()
