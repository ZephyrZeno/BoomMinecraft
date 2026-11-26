"""Bind a file bootstrap kernel test to current accepted normal source layouts."""
import argparse
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('file_bootstrap_probe_source',ROOT/'scripts/runtime-provider-source.py')
S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)


def prepare(provider,side,output):
    provider=Path(provider).resolve();output=Path(output).resolve()
    S.check(output.is_relative_to(S.ART) and not output.exists(),'File test needs a fresh project .boom source record')
    m=S.read(provider);V=S.module('file_bootstrap_probe_independent_verification','verify-runtime-provider-pack.py')
    proof=V.verify(provider,m['base']['batch'],m['base']['plan'])
    S.check(S.read(provider.with_name('verification.json'))==proof and m['family']=='normal-file-bootstrap-v1','File bootstrap independent proof differs')
    current=S.read(S.ART/'current-development-status.json');accepted=Path(current['archive'])/'status.json'
    S.check(S.read(accepted)==current,'Current accepted checkpoint differs from its immutable archive')
    source=current['diagnostic_startup']['System_phase1'][side]
    image=S.checked(source['image']);selection=S.checked(source['selection_verification'])
    S.check(m['base']['batch_summary']['digest']['sha256']==current['full_batch'][side]['summary_sha256'] and
            m['base']['base_compiler_sha256']==current['compiler_sha256'],'File kernel source differs from accepted normal layout batch')
    runtime=Path(current['runtime_directory'])/'boom-runtime.dll'
    S.check(S.digest(runtime)['sha256']==current['runtime_sha256'],'Accepted assembly runtime changed')
    runtime_meta=S.read(runtime.with_name('runtime.json'))
    S.check(all(runtime_meta['sources'].get(k)==v for k,v in m['runtime_kernel_sha256'].items()),'File kernel imported runtime ABI differs')
    meta=S.checked(m['file_bootstrap_metadata']);value=dict(schema=1,metadata=S.read(meta),image=str(image),runtime=str(runtime),
        accepted_checkpoint=S.artifact(accepted),source_native_entries_executed=False,Java_constructors_executed=False,game_started=False,
        inputs=[S.artifact(p) for p in (provider,provider.with_name('verification.json'),meta,image,selection,runtime,
            ROOT/'native/providers/file_bootstrap.asm.inc',ROOT/'tests/host/FileBootstrapProviderProbe.cs')])
    S.write(output,value);return value


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--provider',type=Path,required=True);p.add_argument('--side',choices=('server','client'),required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();v=prepare(a.provider,a.side,a.output);print(json.dumps(dict(source=str(a.output),game_started=False)))
