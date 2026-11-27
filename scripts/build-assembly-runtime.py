"""Build the declared MASM runtime recipe with explicit installed tool paths."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def check(value,message):
    if not value:raise ValueError(message)

def artifact(path):
    path=Path(path).resolve();raw=path.read_bytes()
    return dict(path=str(path),digest=dict(size=len(raw),sha256=hashlib.sha256(raw).hexdigest()))

def source(root,name):
    check(isinstance(name,str) and '\\' not in name and ':' not in name,'Expected a canonical project-relative source')
    path=(root/name).resolve()
    check(path.is_relative_to(root) and name==path.relative_to(root).as_posix() and path.is_file(),'Missing or escaped runtime source')
    return path

def recipe(root,path):
    data=json.loads(Path(path).read_bytes())
    check(set(data)=={'schema','kind','units','link_unit_order','exports','link_flags','sdk_libraries','data_sources','optional_word_plan'},'Runtime recipe schema differs')
    check(data['schema']==1 and data['kind']=='masm-runtime-build-recipe','Invalid runtime recipe')
    names=[row['object'] for row in data['units']]
    check(len(names)==len(set(names))==len(data['link_unit_order']) and set(names)==set(data['link_unit_order']),'Duplicate, missing or extra runtime unit')
    check(all(set(row)=={'source','object'} and re.fullmatch(r'[A-Za-z0-9_-]+\.obj',row['object']) for row in data['units']),'Invalid runtime unit')
    check(len(data['exports'])==len(set(data['exports'])) and all(re.fullmatch(r'[A-Za-z_]\w*',name) for name in data['exports']),'Invalid or duplicate runtime export')
    check(data['link_flags']==['/NOLOGO','/DLL','/NOENTRY','/MACHINE:X64','/DYNAMICBASE','/NXCOMPAT'],'Unexpected runtime LINK flags')
    check(len(data['sdk_libraries'])==len(set(data['sdk_libraries'])) and all(re.fullmatch(r'[A-Za-z0-9_]+\.lib',name) for name in data['sdk_libraries']),'Invalid SDK library list')
    check(len(data['data_sources'])==len(set(data['data_sources'])),'Duplicate runtime data source')
    check(data['optional_word_plan']==dict(object='word-plan.obj',export='boom_get_word_plan',before='layers.obj'),'Optional word plan contract differs')
    for row in data['units']:source(root,row['source'])
    for name in data['data_sources']:source(root,name)
    return data

def plan(root,recipe_file,output,assembler,linker,sdk_lib,word_plan=None):
    root,recipe_file,output,assembler,linker,sdk_lib=map(lambda p:Path(p).resolve(),(root,recipe_file,output,assembler,linker,sdk_lib))
    check(output.is_relative_to(root/'.boom') or output.is_relative_to(root/'dist'),'Runtime output must stay in project outputs')
    check(not output.exists(),'Use a fresh runtime output')
    check(assembler.name.lower()=='ml64.exe' and linker.name.lower()=='link.exe','Expected MASM and native LINK')
    data=recipe(root,recipe_file)
    inputs=[artifact(p) for p in [__file__,recipe_file,assembler,linker,*[source(root,row['source']) for row in data['units']],*[source(root,name) for name in data['data_sources']]]]
    units=[dict(source=str(source(root,row['source'])),object=str(output/row['object'])) for row in data['units']]
    ordered=[str(output/name) for name in data['link_unit_order']]
    exports=list(data['exports'])
    if word_plan is not None:
        word_plan=Path(word_plan).resolve();inputs.append(artifact(word_plan))
        row=data['optional_word_plan'];units.append(dict(source=str(word_plan),object=str(output/row['object'])))
        ordered.insert(ordered.index(str(output/row['before'])),str(output/row['object']));exports.append(row['export'])
    libraries=[sdk_lib/name for name in data['sdk_libraries']]
    inputs.extend(artifact(path) for path in libraries)
    image=output/'boom-runtime.dll'
    link=[*data['link_flags'],*['/EXPORT:'+name for name in exports],'/OUT:"'+str(image)+'"',*['"'+path+'"' for path in ordered],*['"'+str(path)+'"' for path in libraries]]
    return dict(root=str(root),output=str(output),recipe=data,units=units,link_tokens=link,inputs=inputs,assembler=str(assembler),linker=str(linker),image=str(image),word_plan=str(word_plan) if word_plan else None)

def build(model):
    check([artifact(row['path']) for row in model['inputs']]==model['inputs'],'Runtime input changed after planning')
    output=Path(model['output']);check(not output.exists(),'Runtime output is immutable');output.mkdir(parents=True)
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    for index,row in enumerate(model['units']):
        with (output/(str(index)+'-assembler.log')).open('xb') as log:
            result=subprocess.run([model['assembler'],'/nologo','/c','/Fo'+row['object'],row['source']],cwd=model['root'],stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
        check(result.returncode==0,'Runtime assembly failed: '+row['source'])
    response=output/'link.rsp';response.write_text('\n'.join(model['link_tokens'])+'\n',encoding='utf-8')
    check(response.read_text(encoding='utf-8').splitlines()==model['link_tokens'],'Runtime canonical LINK response changed')
    with (output/'link.log').open('xb') as log:
        result=subprocess.run([model['linker'],'@'+str(response)],cwd=model['root'],stdout=log,stderr=subprocess.STDOUT,creationflags=flags)
    check(result.returncode==0,'Runtime link failed; logs are preserved')
    check([artifact(row['path']) for row in model['inputs']]==model['inputs'],'Runtime source, tool or SDK input changed')
    root=Path(model['root']);data=model['recipe']
    metadata=dict(implementation_language='x86-64 MASM assembly',
        sources={row['source']:artifact(source(root,row['source']))['digest']['sha256'] for row in data['units']},
        data_sources={name:artifact(source(root,name))['digest']['sha256'] for name in data['data_sources']},
        dll=model['image'],sha256=artifact(model['image'])['digest']['sha256'],java_runtime=False,rust_runtime=False,c_runtime=False)
    (output/'runtime.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    receipt=dict(schema=1,scope='declared_pure_MASM_runtime_build_only',plan=model,
        objects=[artifact(row['object']) for row in model['units']],runtime=artifact(model['image']),
        import_library=artifact(output/'boom-runtime.lib'),metadata=artifact(output/'runtime.json'),link_response=artifact(response),
        linked=True,executed=False,independent_runtime_behavior_verified=False)
    (output/'build.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    return output/'runtime.json'

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--recipe',type=Path,required=True)
    for name in ('output','assembler','linker','sdk-lib'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--word-plan',type=Path);parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args();model=plan(args.root,args.recipe,args.output,args.assembler,args.linker,args.sdk_lib,args.word_plan)
    print(json.dumps(model,indent=2) if args.dry_run else build(model))

if __name__=='__main__':main()
