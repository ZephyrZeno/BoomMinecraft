"""Build the player launcher, compiler backend and original packaging probe.

All build tools and generated outputs are explicit. The UI is never launched.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def check(value,message):
    if not value:raise ValueError(message)

def artifact(path):
    path=Path(path).resolve()
    with path.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    return dict(path=str(path),digest=dict(size=path.stat().st_size,sha256=digest))

def module(file):
    spec=importlib.util.spec_from_file_location('launcher_build_'+file.replace('-','_'),Path(__file__).with_name(file))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def source_inputs(root):
    files={root/'Cargo.toml',root/'Cargo.lock',root/'launcher/Launcher.cs',root/'third_party/unicode/LICENSE.txt'}
    for path in (root/'src').rglob('*.rs'):
        files.add(path)
        for value in re.findall(r'include_(?:str|bytes)!\(\s*"([^"]+)"',path.read_text(encoding='utf-8-sig')):
            resolved=(path.parent/value).resolve();check(resolved.is_relative_to(root),'Rust include escaped project');files.add(resolved)
    return [artifact(p) for p in sorted(files)]

def build(root,output,cargo,rustc,csc,target_dir,javac,assembler,linker,sdk_lib,dumpbin,recipe,*,offline=False,jobs=2):
    root,output,cargo,rustc,csc,target_dir=map(lambda p:Path(p).resolve(),(root,output,cargo,rustc,csc,target_dir))
    check(output.is_relative_to(root/'.boom') or output.is_relative_to(root/'dist'),'Launcher output must stay in project outputs')
    check(target_dir.is_relative_to(root/'.boom'),'Use a project-private .boom Cargo target directory')
    check(not output.exists() and not target_dir.is_relative_to(output),'Fresh output and separate private Cargo cache required')
    check(1<=jobs<=8,'Launcher compiler jobs must be1..8')
    probe=module('build-native-probe.py')
    inputs=source_inputs(root)+[artifact(p) for p in (__file__,cargo,rustc,csc,probe.__file__,Path(__file__).with_name('build-assembly-runtime.py'),recipe,javac,assembler,linker,dumpbin)]
    output.mkdir(parents=True)
    try:
        env=dict(os.environ);env['RUSTC']=str(rustc);env.pop('RUSTC_WRAPPER',None);env.pop('RUSTC_WORKSPACE_WRAPPER',None)
        args=[cargo,'build','--release','--locked','--bin','boom','--target-dir',target_dir,'--jobs',str(jobs)]
        if offline:args.append('--offline')
        with (output/'cargo.log').open('xb') as out,(output/'cargo.err').open('xb') as err:
            result=subprocess.run([str(v) for v in args],cwd=root,env=env,stdout=out,stderr=err,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        check(result.returncode==0,'Launcher backend compilation failed; logs are preserved')
        calls=[dict(command=[str(v) for v in args],exit_code=result.returncode,stdout=artifact(output/'cargo.log'),stderr=artifact(output/'cargo.err'))]
        binary=target_dir/'release/boom.exe';check(binary.is_file(),'Cargo did not produce boom.exe')
        shutil.copyfile(binary,output/'boom.exe')
        licenses=output/'licenses';licenses.mkdir();shutil.copyfile(root/'third_party/unicode/LICENSE.txt',licenses/'unicode.txt')
        args=[csc,'/nologo','/target:winexe','/platform:x64','/optimize+','/codepage:65001','/out:'+str(output/'BoomLauncher.exe'),
            '/reference:System.Drawing.dll','/reference:System.Windows.Forms.dll','/reference:System.Core.dll','/reference:System.Web.Extensions.dll',root/'launcher/Launcher.cs']
        calls.append(probe.command(args,output,'launcher-csc',cwd=root))
        native=probe.build(root,output/'native',output/'boom.exe',javac,assembler,linker,sdk_lib,dumpbin,recipe)
        check([artifact(p['path']) for p in inputs]==inputs,'Launcher source/tool input changed during packaging')
        check(artifact(binary)['digest']==artifact(output/'boom.exe')['digest'],'Packaged compiler differs from Cargo output')
        record=dict(schema=1,scope='launcher_and_backend_build_with_original_packaging_development_probe',inputs=inputs,calls=calls,
            launcher=artifact(output/'BoomLauncher.exe'),compiler=artifact(output/'boom.exe'),native_probe=artifact(native),
            license=artifact(licenses/'unicode.txt'),passed=True,UI_launched=False,game_started=False,full_game_ready=False)
        with (output/'build.json').open('x',encoding='utf-8') as stream:json.dump(record,stream,indent=2);stream.write('\n')
        return output/'build.json'
    except BaseException as error:
        with (output/'first-failure.json').open('x',encoding='utf-8') as stream:json.dump(dict(error=repr(error),UI_launched=False,game_started=False),stream);stream.write('\n')
        raise

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT)
    for name in ('output','cargo','rustc','csc','target-dir','javac','assembler','linker','sdk-lib','dumpbin','recipe'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--offline',action='store_true');p.add_argument('--jobs',type=int,default=2)
    a=p.parse_args();print(build(a.root,a.output,a.cargo,a.rustc,a.csc,a.target_dir,a.javac,a.assembler,a.linker,a.sdk_lib,a.dumpbin,a.recipe,offline=a.offline,jobs=a.jobs))

if __name__=='__main__':main()
