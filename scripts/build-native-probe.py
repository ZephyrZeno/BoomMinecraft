"""Build the MASM runtime and run the original isolated integer development probe.

This developer probe is part of launcher packaging verification. It is not a
Minecraft startup, a JVM runtime, or a complete runtime behavior test.
"""
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
    path=Path(path).resolve()
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),digest=dict(size=path.stat().st_size,sha256=digest))

def module(file):
    spec=importlib.util.spec_from_file_location('native_probe_'+file.replace('-','_'),Path(__file__).with_name(file))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def command(args,output,name,*,cwd,timeout=None):
    with (output/(name+'.log')).open('xb') as out,(output/(name+'.err')).open('xb') as err:
        result=subprocess.run([str(p) for p in args],cwd=cwd,stdout=out,stderr=err,timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    check(result.returncode==0,'Developer native probe step failed: '+name)
    return dict(command=[str(p) for p in args],exit_code=result.returncode,stdout=artifact(output/(name+'.log')),stderr=artifact(output/(name+'.err')))

def build(root,output,boom,javac,assembler,linker,sdk_lib,dumpbin,recipe):
    root,output,boom,javac,assembler,linker,sdk_lib,dumpbin,recipe=map(lambda p:Path(p).resolve(),
        (root,output,boom,javac,assembler,linker,sdk_lib,dumpbin,recipe))
    check(output.is_relative_to(root/'.boom') or output.is_relative_to(root/'dist'),'Probe output must stay in project outputs')
    check(not output.exists(),'Probe output is immutable; use a fresh directory')
    runtime=module('build-assembly-runtime.py')
    original=root/'java/subset/dev/boom/subset/IntKernels.java'
    native=root/'native/probe/main.asm'
    inputs=[artifact(p) for p in (__file__,runtime.__file__,boom,javac,assembler,linker,dumpbin,recipe,original,native,sdk_lib/'kernel32.lib')]
    output.mkdir(parents=True)
    try:
        runtime_dir=output/'runtime'
        runtime_result=runtime.build(runtime.plan(root,recipe,runtime_dir,assembler,linker,sdk_lib))
        classes=output/'fixture-classes';classes.mkdir()
        calls=[command([javac,'--release','21','-d',classes,original],output,'javac',cwd=root)]
        kernel=output/'kernel'
        calls.append(command([boom,'compile-asm','--class-file',classes/'dev/boom/subset/IntKernels.class','--method','parallelWork',
            '--output',kernel,'--assemble'],output,'compile',cwd=root))
        obj=output/'probe.obj';image=output/'boom-native-probe.exe'
        calls.append(command([assembler,'/nologo','/c','/Fo'+str(obj),native],output,'probe-assemble',cwd=root))
        tokens=['/NOLOGO','/SUBSYSTEM:CONSOLE','/ENTRY:boom_probe_main','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT',
            '/OUT:"'+str(image)+'"',*['"'+str(p)+'"' for p in (obj,runtime_dir/'parallel.obj',kernel/'method.obj',sdk_lib/'kernel32.lib')]]
        response=output/'link.rsp';response.write_text('\n'.join(tokens)+'\n',encoding='utf-8')
        check(response.read_text(encoding='utf-8').splitlines()==tokens,'Developer probe LINK response changed')
        calls.append(command([linker,'@'+str(response)],output,'probe-link',cwd=root))
        calls.append(command([image],output,'probe-execute',cwd=output,timeout=45))
        calls.append(command([dumpbin,'/DEPENDENTS',image],output,'probe-dependencies',cwd=root))
        check([artifact(p['path']) for p in inputs]==inputs,'Native probe input changed')
        record=dict(schema=1,scope='original_integer_development_probe_and_pure_MASM_runtime_build',inputs=inputs,calls=calls,
            runtime_metadata=artifact(runtime_result),runtime_build=artifact(runtime_dir/'build.json'),
            source_fixture=artifact(classes/'dev/boom/subset/IntKernels.class'),compiler_manifest=artifact(kernel/'compilation.json'),
            image=artifact(image),link_response=artifact(response),passed=True,game_started=False,full_runtime_behavior_proven=False)
        with (output/'result.json').open('x',encoding='utf-8') as stream:json.dump(record,stream,indent=2);stream.write('\n')
        return output/'result.json'
    except BaseException as error:
        with (output/'first-failure.json').open('x',encoding='utf-8') as stream:json.dump(dict(error=repr(error),game_started=False),stream);stream.write('\n')
        raise

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT)
    for name in ('output','boom','javac','assembler','linker','sdk-lib','dumpbin','recipe'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();print(build(a.root,a.output,a.boom,a.javac,a.assembler,a.linker,a.sdk_lib,a.dumpbin,a.recipe))

if __name__=='__main__':main()
