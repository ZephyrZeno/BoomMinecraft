"""Reject an actual executable COFF mutation without linking or running it."""
import argparse
from copy import deepcopy
import importlib.util
from pathlib import Path
import struct
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('method_invoke_negative_candidate',ROOT/'scripts/method-invoke-candidate.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
S=B.S


def run(candidate_file,output):
    original=S.read(candidate_file);positive=B.verify(candidate_file)
    S.check(positive==S.read(candidate_file.with_name('verification.json')),'Original current candidate positive control differs')
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh isolated negative output required')
    output.mkdir(parents=True);obj=S.checked(original['object']);before=S.artifact(obj)
    data=bytearray(obj.read_bytes())
    S.check(len(data)>=20 and struct.unpack_from('<H',data)[0]==0x8664,'Expected ordinary AMD64 COFF')
    count=struct.unpack_from('<H',data,2)[0];optional=struct.unpack_from('<H',data,16)[0]
    S.check(0<count<=96 and len(data)>=20+optional+40*count,'Actual source COFF section table is invalid')
    for index in range(count):
        at=20+optional+40*index;name=bytes(data[at:at+8]).rstrip(b'\0')
        size,pointer=struct.unpack_from('<II',data,at+16);flags=struct.unpack_from('<I',data,at+36)[0]
        if name.startswith(b'.text') and flags&0x20000000 and size:break
    else:raise ValueError('Actual source COFF has no executable text section')
    S.check(pointer+size<=len(data),'Actual executable section exceeds the COFF input')
    previous=data[pointer];data[pointer]^=1;mutant=output/'mutated-executable.obj';mutant.write_bytes(data)
    value=deepcopy(original);value['object']=S.artifact(mutant);negative=output/'candidate.json';S.write(negative,value)
    try:B.verify(negative)
    except ValueError as error:
        observed=str(error)
        S.check(observed=='Method invoke actual code/data/unwind/all relocations differ from canonical',
            'Mutation did not reach the actual source/machine comparison: '+observed)
    else:raise ValueError('Actual executable mutation was accepted')
    S.check(S.artifact(obj)==before and S.artifact(candidate_file)==positive['candidate'],'Original source candidate/object changed')
    result=dict(schema=1,verified=True,scope='actual_executable_COFF_mutation_rejected_before_link_or_guest',
        tool=S.artifact(Path(__file__)),original=S.artifact(candidate_file),positive_source_machine_proof=positive,
        original_object=before,negative=S.artifact(negative),mutant_object=S.artifact(mutant),
        section=name.decode('ascii'),file_offset=pointer,before=previous,after=data[pointer],observed_error=observed,
        production_or_original_input_changed=False,linked=False,executed=False,game_started=False)
    path=output/'result.json';S.write(path,result);return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=S.ART/'method-invoke'/('negative-'+uuid4().hex))
    args=parser.parse_args();print(run(args.candidate.resolve(),args.output))
