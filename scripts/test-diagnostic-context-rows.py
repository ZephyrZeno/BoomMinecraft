"""Exercise generated diagnostic stubs on distinct OS threads with a shared first-stop pool."""
import argparse
import ctypes as c
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
from threading import Barrier
from uuid import uuid4


def run(model_file, assembler, linker, output):
    spec = importlib.util.spec_from_file_location('source_diagnostic_context_fixture', model_file)
    model = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(model)
    frontiers = [dict(kind='method', symbol=f'boom_m{i}', reason='fixture native', binding=None, class_id=1,
                      source_sha256='f'*64, method=dict(id=i, name='fixture', descriptor='()V', code_sha256=None,
                      stage='declaration', assembly_emitted=False, assembly_unit=None)) for i in (10, 20)]
    output.mkdir(parents=True)
    model.publish(output, frontiers, [], context_rows=True)
    obj, dll = output/'stops.obj', output/'stops.dll'
    subprocess.run([str(assembler), '/nologo', '/c', '/Fo'+str(obj), str(output/'diagnostic-stops.asm')], check=True)
    symbols = ['boom_m10','boom_m20','boom_diagnostic_pool','boom_diagnostic_context_map','boom_diagnostic_context_map_row']
    subprocess.run([str(linker), '/NOLOGO', '/DLL', '/NOENTRY', '/MACHINE:X64', '/OUT:'+str(dll), str(obj),
                    *('/EXPORT:'+s for s in symbols)], check=True)
    image = c.CDLL(str(dll))
    pool = c.addressof(c.c_ubyte.in_dll(image, 'boom_diagnostic_pool'))
    sidecar = c.addressof(c.c_ubyte.in_dll(image, 'boom_diagnostic_context_map'))
    get = image.boom_diagnostic_context_map_row
    get.argtypes, get.restype = (c.c_void_p,c.c_void_p), c.c_uint32
    stops = [image.boom_m10, image.boom_m20]
    for f in stops:
        f.argtypes, f.restype = [c.c_void_p], c.c_uint64
    contexts = [(c.c_uint64*4)(17<<32, 19, 0, 1234+i) for i in range(32)]
    gate = Barrier(len(contexts), timeout=15)

    def execute(i):
        ctx = contexts[i]
        row = (i & 1)+1
        gate.wait()
        if stops[row-1](ctx) or get(ctx,sidecar)!=row or list(ctx)!=[(17<<32)|0xb001,19,0,1234+i]:
            raise ValueError('Per-context row, PC, method or VM plan differs')
        if stops[2-row](ctx) or get(ctx,sidecar)!=row:
            raise ValueError('A pending error replaced a context row')

    with ThreadPoolExecutor(len(contexts)) as workers:
        list(workers.map(execute, range(len(contexts))))
    first = c.c_uint32.from_address(pool+32).value
    owner = c.c_void_p.from_address(pool+80).value
    if first not in (1,2) or get(owner,sidecar)!=first or c.c_uint32.from_address(sidecar+28).value:
        raise ValueError('Process-first row or map overflow accounting differs')
    result=dict(passed=True, scope='generated_diagnostic_stubs_only', parallel_OS_threads=len(contexts),
                first_process_row=first, distinct_source_rows=2, pending_errors_preserved=True,
                VM_plan_preserved=True, game_started=False)
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assembler',type=Path,required=True)
    parser.add_argument('--linker',type=Path,required=True)
    parser.add_argument('--model',type=Path,default=Path(__file__).with_name('diagnostic-closure.py'))
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]/'.boom/diagnostic-context-routing-tests'/uuid4().hex
    run(args.model,args.assembler,args.linker,root)
    print(root)
