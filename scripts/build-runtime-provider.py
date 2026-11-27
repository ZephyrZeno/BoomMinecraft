"""Prepare, assemble, seal and independently verify one source-bound provider."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def check(value,message):
    if not value:raise ValueError(message)

def artifact(path):
    path=Path(path).resolve();raw=path.read_bytes()
    return dict(path=str(path),digest=dict(size=len(raw),sha256=hashlib.sha256(raw).hexdigest()))

def module(root,file):
    spec=importlib.util.spec_from_file_location('provider_build_'+file.replace('-','_'),Path(root)/'scripts'/file)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

def build(root,batch,plan,output,family,assembler,frame_overlay=None):
    root,batch,plan,output,assembler=map(lambda p:Path(p).resolve(),(root,batch,plan,output,assembler))
    check(output.is_relative_to(root/'.boom/runtime-providers') and not output.exists(),'Use a fresh project provider output')
    check(assembler.name.lower()=='ml64.exe','Use the x64 MASM assembler')
    producer=module(root,'build-runtime-provider-pack.py')
    verifier=module(root,'verify-runtime-provider-pack.py')
    original_tools=producer.S.tools_identity()
    pins=[artifact(p) for p in (Path(__file__),assembler,root/'scripts/build-runtime-provider-pack.py',root/'scripts/verify-runtime-provider-pack.py')]
    prepared=producer.prepare(batch,plan,output,family,frame_overlay)
    check(prepared['tool_sources']==original_tools,'Provider tools changed during prepare')
    with (output/'assembler.log').open('xb') as log:
        command=[str(assembler),'/nologo','/c','/Fo'+str(output/'provider.obj'),str(output/'provider.asm')]
        result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    check(result.returncode==0,'Provider assembly failed; assembler.log is preserved')
    check([artifact(p['path']) for p in pins]==pins,'Provider builder or assembler changed during build')
    manifest=producer.seal(output,assembler)
    proof=verifier.verify(output/'provider.json',batch,plan)
    check(proof.get('verified') is True,'Independent provider verification did not pass')
    producer.S.write(output/'verification.json',proof)
    check(producer.S.tools_identity()==original_tools and [artifact(p['path']) for p in pins]==pins,'Provider inputs changed during verification')
    record=dict(schema=1,scope='source_bound_provider_prepare_assemble_seal_and_independent_verify',
        provider=artifact(output/'provider.json'),verification=artifact(output/'verification.json'),
        builder=artifact(__file__),inputs=pins,tool_sources=original_tools,
        assembler_command=command,source_generator_returned_family=manifest['family'],
        verified=True,executed=False,game_started=False)
    producer.S.write(output/'build.json',record)
    return output/'provider.json'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    for name in ('batch','plan','output','assembler'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--family',required=True);parser.add_argument('--frame-overlay',type=Path)
    args=parser.parse_args()
    print(build(args.root,args.batch,args.plan,args.output,args.family,args.assembler,args.frame_overlay))

if __name__=='__main__':main()
