"""Discover supported original metafactory sites from an actual source selection.

No caller names or method IDs select a rule. Unsupported original sites retain
their exact source identity and a deferred reason; this never accepts a runtime.
"""
import argparse
import importlib.util
from pathlib import Path
import re


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('lambda_discovery_contract',ROOT/'scripts/normal-lambda-source.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
S=C.S


def discover(selection):
    closure_file=selection/'closure.json';diagnostic_file=selection/'diagnostic.json'
    closure=S.read(closure_file);diagnostic=S.read(diagnostic_file)
    sources=C.Sources(Path(closure['batch']),Path(closure['plan']))
    S.check(closure['source_batch_summary_sha256']==sources.base['batch_summary']['digest']['sha256'],
        'Selected source belongs to another original batch')
    considered={};selected=[];deferred=[];other=[]
    for row in diagnostic['rows']:
        match=re.fullmatch(r'boom_batch_call_(\d+)_(\d+)_186',row['symbol'])
        if row['category']!=3 or match is None:continue
        ident,constant=map(int,match.groups());key=ident,constant
        if key in considered:continue
        cls=sources.classes[ident];raw=sources.raw(cls)
        S.check(raw.cp[constant][0]==18 and cls['origin']['sha256']==row['source_sha256'],
            'Selected indy diagnostic differs from locked original class/constant')
        bootstrap=raw.cp[constant][1][0];handle=C.handle(raw,raw.bootstraps[bootstrap][0])
        request=cls['origin']['loader']+':'+cls['name']+':'+str(constant)
        identity=dict(request=request,binding=row['symbol'],class_id=ident,constant=constant,
            source_sha256=cls['origin']['sha256'],original_bootstrap=handle,diagnostic_row=row['id'])
        considered[key]=identity
        if handle['owner']!=C.BOOTSTRAP:
            other.append(dict(**identity,expanded=False,reason='not_standard_LambdaMetafactory_protocol'));continue
        try:
            contract=C.site(sources,cls,constant)
            C.require(not contract['captures'],'capturing_UFMP_metadata_extension_not_yet_implemented')
            selected.append(dict(**identity,rule=contract['rule'],sam_descriptor=contract['sam_descriptor'],
                implementation=contract['implementation'],required_Java_method=contract['implementation_member'],
                required_bootstrap_class=contract['bootstrap_member']['class_id']))
        except C.Deferred as error:deferred.append(dict(**identity,expanded=False,reason=str(error)))
    selected.sort(key=lambda row:(row['class_id'],row['constant']));deferred.sort(key=lambda row:(row['class_id'],row['constant']))
    other.sort(key=lambda row:(row['class_id'],row['constant']))
    return sources,dict(schema=1,scope='source_shape_discovery_only_no_runtime_acceptance',
        selection=S.artifact(closure_file),diagnostic=S.artifact(diagnostic_file),base=sources.base,
        tool=S.artifact(Path(__file__)),source_rule=S.artifact(ROOT/'scripts/normal-lambda-source.py'),
        supported=selected,deferred=deferred,other_protocols=other,total_original_indy_sites=len(considered),
        selection_by_bootstrap_signature_access_and_type_adaptation=True,caller_method_special_cases=False,
        new_Java_dependencies_admitted_automatically=False,production_batch_verification=False,
        source_shape_coverage_is_runtime_execution_coverage=False,executed=False,game_started=False)


def prepare(selection,output,assembler=None):
    _,discovery=discover(selection);E=C.module('normal-lambda-expansion')
    S.check(discovery['supported'],'No supported noncapturing original metafactory sites in this selection')
    manifest=E.prepare(Path(discovery['base']['batch']),Path(discovery['base']['plan']),
        [row['request'] for row in discovery['supported']],output)
    discovery['expansion']=S.artifact(manifest);S.write(output.resolve()/'discovery.json',discovery)
    if assembler:E.assemble(manifest,assembler)
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--selection',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--assembler',type=Path);args=parser.parse_args()
    print(prepare(args.selection.resolve(),args.output,args.assembler.resolve() if args.assembler else None))
