"""Reseal deliberately corrupted real derived COFF; require semantic rejection."""
import argparse
import copy
import importlib.util
from pathlib import Path
import struct


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('lambda_negative_verifier',ROOT/'scripts/verify-normal-lambda-overlay.py')
V=importlib.util.module_from_spec(spec);spec.loader.exec_module(V)
S=V.S;C=V.C


def cell(raw,obj,name,offset,width,value):
    row=obj.symbols[name];header=20+(row['section']-1)*40
    data=struct.unpack_from('<I',raw,header+20)[0];at=data+row['value']+offset
    S.check(data>0 and 0<=at and at+width<=len(raw),'Negative fixture cell is outside COFF section')
    before=int.from_bytes(raw[at:at+width],'little');S.check(before!=value,'Negative fixture must change an ABI cell')
    raw[at:at+width]=value.to_bytes(width,'little');return dict(symbol=name,offset=offset,width=width,before=before,after=value)


def run(overlay_file,output):
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh isolated metadata negative output required')
    positive=V.verify(overlay_file);original=S.read(overlay_file);manifest=S.read(S.checked(original['expansion']));[generated]=manifest['generated']
    S.check(positive==S.read(overlay_file.with_name('verification.json')),'Full positive current-source/COFF verification differs')
    output.mkdir(parents=True);cases=[];tid=generated['type_id'];frame=generated['methods'][0]
    specifications=[
        ('runtime-capacity','runtime-globals','boom_runtime_type_map',12,4,tid,'Actual runtime type capacity differs'),
        ('Class-root-count','Class-identities-and-names','boom_java_class_root_count',0,8,
            manifest['original_ranges']['types'],'Actual normal root span/count differs'),
        ('Class-host-module','Class-identities-and-names','boom_java_class_records',tid*48+20,4,63,'Actual generated Class identity differs: module'),
        ('frame-Code-length','contiguous-frames','boom_trace_method'+str(frame['id']),16,4,frame['code_length']+1,
            'Actual generated frame row is outside the contiguous bank')]
    [dispatch]=[u for u in original['units'] if u['role']=='selected-dispatch']
    [sam_table]=[t for t in dispatch['detail']['tables'] if t['appended_rows'][0]['target']==generated['methods'][-1]['id']]
    specifications.append(('dispatch-receiver','selected-dispatch','boom_batch_vrows'+str(sam_table['id']),
        sam_table['original_rows']*16,4,tid+1,'Actual synthetic dispatch receiver/error differs'))
    for key,role,symbol,offset,width,value,expected in specifications:
        directory=output/key;directory.mkdir();[unit]=[u for u in original['units'] if u['role']==role]
        obj=S.checked(unit['object']);parsed=V.P.Coff(obj);raw=bytearray(obj.read_bytes())
        mutation=cell(raw,parsed,symbol,offset,width,value);changed=directory/'corrupted.obj';changed.write_bytes(raw)
        altered=copy.deepcopy(original);[target]=[u for u in altered['units'] if u['role']==role]
        target['object']=S.artifact(changed);file=directory/'overlay.json';S.write(file,altered)
        try:V.verify(file)
        except ValueError as error:
            S.check(expected in str(error),'Negative fixture failed an unrelated guard: '+str(error))
            cases.append(dict(name=key,object=S.artifact(changed),resealed_overlay=S.artifact(file),mutation=mutation,
                rejected=True,semantic_error=str(error),input_hash_check_intentionally_passed=True))
        else:raise ValueError('Resealed corrupted actual metadata was accepted: '+key)
    for unit in original['units']:S.checked(unit['assembly']);S.checked(unit['object'])
    S.check(S.artifact(overlay_file)==positive['overlay'],'Negative tests changed their positive input')
    proof=dict(schema=1,verified=True,scope='resealed_actual_COFF_metadata_negative_regressions',positive_overlay=S.artifact(overlay_file),
        positive_verification=S.artifact(overlay_file.with_name('verification.json')),tool=S.artifact(Path(__file__)),
        verifier=S.artifact(ROOT/'scripts/verify-normal-lambda-overlay.py'),cases=cases,
        original_source_and_COFF_files_modified=False,provider_validation_skipped=False,executed=False,game_started=False)
    file=output/'result.json';S.write(file,proof);return file


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--overlay',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();print(run(args.overlay.resolve(),args.output))
