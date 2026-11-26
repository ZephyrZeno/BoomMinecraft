"""Recheck sealed cold Map evidence with a complete JDK catalog digest check."""
import argparse
import ast
import copy
import hashlib
import importlib.util
from pathlib import Path
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
ORIGINAL=ROOT/'scripts/test-formal-map-library-name.py'
spec=importlib.util.spec_from_file_location('sealed_formal_map_harness',ORIGINAL)
T=importlib.util.module_from_spec(spec);spec.loader.exec_module(T)
S,F=T.S,T.F


def dump(node):return ast.dump(node,include_attributes=False)


def run(images_file,output):
    images_file,output=Path(images_file).resolve(),Path(output).resolve()
    S.check(output.is_relative_to(S.ART) and not output.exists(),'Use a fresh isolated Map recheck directory')
    original_record=S.artifact(ORIGINAL);tool=S.artifact(__file__);helper=S.artifact(F.__file__)
    images=S.read(images_file)
    S.check(original_record in images['harness_sources'],'Original Map execution harness is not sealed by this source image')
    failure=images_file.parent/'execution-result.json';old=S.read(failure)
    S.check(old.get('verified') is False and old.get('error')=="ValueError('Locked JDK module image changed')",
            'Recheck requires the preserved catalog-digest false negative')
    inputs=[original_record,tool,helper,S.artifact(images_file),S.artifact(failure),images['source_selection']]
    output.mkdir(parents=True)
    tree=ast.parse(ORIGINAL.read_text(encoding='utf-8'),filename=str(ORIGINAL))
    original={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
    execute=copy.deepcopy(original['execute']);oracle=copy.deepcopy(original['oracle'])
    old_directory=ast.parse("images_file.parent/'oracle'",mode='eval').body
    new_directory=ast.parse(repr(str(output/'oracle')),mode='eval').body
    new_directory=ast.Call(func=ast.Name(id='Path',ctx=ast.Load()),args=[new_directory],keywords=[])
    old_comparison=ast.parse("S.digest(record['path'])==record['digest']",mode='eval').body
    new_comparison=ast.parse('_complete_catalog_digests_match(record)',mode='eval').body
    changed_directory=changed_comparison=0
    for statement in execute.body:
        if isinstance(statement,ast.Assign) and dump(statement.value)==dump(old_directory):
            S.check(len(statement.targets)==1 and isinstance(statement.targets[0],ast.Name) and
                    statement.targets[0].id=='oracle_dir','Unexpected Map oracle directory assignment')
            statement.value=ast.copy_location(copy.deepcopy(new_directory),statement.value);changed_directory+=1
    for node in ast.walk(oracle):
        if isinstance(node,ast.Call):
            for i,argument in enumerate(node.args):
                if dump(argument)==dump(old_comparison):
                    node.args[i]=ast.copy_location(copy.deepcopy(new_comparison),argument);changed_comparison+=1
    S.check((changed_directory,changed_comparison)==(1,1),'Original Map harness no longer has the two exact recheck sites')
    restored_execute=copy.deepcopy(execute);restored_oracle=copy.deepcopy(oracle)
    for statement in restored_execute.body:
        if isinstance(statement,ast.Assign) and dump(statement.value)==dump(new_directory):statement.value=copy.deepcopy(old_directory)
    for node in ast.walk(restored_oracle):
        if isinstance(node,ast.Call):
            for i,argument in enumerate(node.args):
                if dump(argument)==dump(new_comparison):node.args[i]=copy.deepcopy(old_comparison)
    S.check(dump(restored_execute)==dump(original['execute']) and dump(restored_oracle)==dump(original['oracle']),
            'Map recheck altered runtime/GC/cleanup or the JDK 19-case program/assertions')
    S.check(dump(execute.body[0])==dump(ast.parse('F.verify(images_file)').body[0]),
            'Map recheck must retain the full fresh source verifier')
    proof=dict(original_harness=original_record,recheck_harness=tool,helper=helper,
        full_F_verify_retained=True,runtime_GC_cleanup_AST_unchanged=True,
        original_execute_ast=dump(original['execute']),recheck_execute_ast=dump(execute),
        original_oracle_ast=dump(original['oracle']),recheck_oracle_ast=dump(oracle),
        only_execute_change='oracle output directory in the new recheck output',
        only_oracle_change='compute and compare all catalog size/SHA1/SHA256 fields',
        JDK_19_case_source_command_and_output_assertion_AST_unchanged=True)
    ast_file=output/'harness-AST-proof.json';S.write(ast_file,proof)
    digest_checks=[]
    def complete_catalog_digests_match(record):
        path=Path(record['path']).resolve()
        S.check(path.is_relative_to(Path('D:/Dev')) or path.is_relative_to(S.ART),
                'Locked oracle catalog escaped the isolated tool/input roots')
        S.check(set(record['digest'])=={'size','sha1','sha256'},'Unexpected locked JDK catalog digest fields')
        sha1,sha256=hashlib.sha1(),hashlib.sha256();size=0
        with path.open('rb') as stream:
            while chunk:=stream.read(2<<20):
                size+=len(chunk);sha1.update(chunk);sha256.update(chunk)
        actual=dict(size=size,sha1=sha1.hexdigest(),sha256=sha256.hexdigest())
        digest_checks.append(dict(path=str(path),expected=record['digest'],actual=actual,verified=actual==record['digest']))
        return actual==record['digest']
    namespace=dict(vars(T));namespace['_complete_catalog_digests_match']=complete_catalog_digests_match
    compiled=ast.fix_missing_locations(ast.Module(body=[oracle,execute],type_ignores=[]))
    exec(compile(compiled,str(Path(__file__).resolve()),'exec'),namespace)
    result=namespace['execute'](images_file)
    S.check(len(digest_checks)==1 and digest_checks[0]['verified'],'Locked catalog full-digest comparison did not execute')
    digest_file=output/'locked-catalog-digests.json';S.write(digest_file,digest_checks)
    for record in inputs:F.checked(record)
    result.update(recheck_harness=tool,source_harness=original_record,source_helper=helper,
        source_harness_AST_proof=S.artifact(ast_file),locked_JDK_all_catalog_digests=S.artifact(digest_file),
        preserved_original_failure=S.artifact(failure),original_source_verification=images['source_selection'],
        source_or_COFF_or_existing_receipts_modified=False,source_selection_prepared_again=False,
        verifier_bypassed=False,recheck_inputs=inputs)
    path=output/'result.json';S.write(path,result);return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--images',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=S.ART/'formal-map-library-name-rechecks'/uuid4().hex)
    args=parser.parse_args();print(run(args.images,args.output))
