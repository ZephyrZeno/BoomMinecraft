"""Exercise ASM root snapshots in accepted original-Java IO/Parker source images."""
import argparse
import ast
from collections import Counter
import ctypes as c
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]


def module(file):
    spec=importlib.util.spec_from_file_location('native_roots_'+file,ROOT/'scripts'/(file+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


N=module('provider-native-roots');K=module('test-unsafe-park');S=K.S
P,U,Q=K.Ptr,K.U,K.Q
KERNEL=ROOT/'native/kernels/provider_native_root_snapshot.asm.inc'
BASE_SPANS=N.STANDARD_SOURCE_SPANS+[N.PRIMORDIAL_SPAN]
EXPORTED={'boom_provider_native_roots_snapshot','boom_provider_native_roots_full_snapshot',
    'boom_selected_provider_root_spans','boom_selected_provider_root_span_count','boom_selected_provider_root_cell_count'}
SNAPSHOTS=[]


class LiveIO:
    def __init__(self,image,java,new,string,field,images,kind):
        self.image,self.java,self.field=image,java,field
        self.path=images.parent/(kind+'-native-root-live.bin');self.path.write_bytes(b'Q-rooted-owned-file')
        self.stream=new('java/io/FileInputStream')
        java('java/io/FileInputStream','<init>','(Ljava/lang/String;)V',[self.stream,string(str(self.path))])
        self.fd=field(self.stream,'java/io/FileInputStream','fd')
        S.check(self.fd in (Q*4096).from_address(K.addr(image,'boom_file_input_owner_roots')),'Original IO open did not publish a real native FD owner')
    def verify_and_close(self,heap,contains):
        S.check(contains(heap,self.stream) and contains(heap,self.fd),'ASM snapshot omitted native FD owner or original FD.parent/FIS graph')
        S.check(self.java('java/io/FileInputStream','read','()I',[self.stream])==ord('Q'),'Rooted original FIS graph could not read after actual GC')
        self.java('java/io/FileInputStream','close','()V',[self.stream])
        S.check(not any((Q*4096).from_address(K.addr(self.image,'boom_file_input_owner_roots'))),'Original source IO close failed to remove its native root')


def fd_bank(bank,owner):
    values=[oop for oop in bank if oop]
    S.check(values in ([],[owner.fd]),'Unexpected active FD root during native snapshot fixture')
    return True


def snapshot(image,values,images,collections):
    buffer=(Q*1048576)();count=Q(0xabcdef)
    code=K.proc(image,'boom_provider_native_roots_full_snapshot',U,P,U,P)(buffer,1048576,c.byref(count))
    S.check(code==0 and count.value<=1048576,'Actual ASM full normal/native root snapshot failed')
    vector=(Q*count.value).from_buffer(buffer)
    S.check(Counter(vector)==Counter(values),'ASM snapshot omitted, added or duplicated a physical non-null source root cell')
    SNAPSHOTS.append(dict(index=len(collections),actual_non_null_cells=count.value,expected_non_null_cells=len(values),
        complete_multiset_equality=True,duplicates_retained=True,vector_sha256=hashlib.sha256(bytes(vector)).hexdigest(),
        root_values_written_by_ASM=False,collector_vector_written_by_ASM=True))
    return vector


def adapted_semantics():
    original=inspect.getsource(K.semantics);tree=ast.parse(original);fn=tree.body[0]
    [collection]=[node for node in fn.body if isinstance(node,ast.FunctionDef) and node.name=='collection']
    changes=[]
    before=[i for i,node in enumerate(fn.body) if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and
        ast.unparse(node.value).startswith("result.update(null_and_unstarted_unpark_no_op=True")]
    S.check(len(before)==1,'Frozen Parker pre-quiescence test anchor changed')
    fn.body.insert(before[0],ast.parse('io_owner=LiveIO(image,java,new,string,field,images_file,kind)').body[0]);changes.append('normal source FIS open before worker quiescence')
    for node in ast.walk(collection):
        if (isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='check' and len(node.args)==2 and
                isinstance(node.args[1],ast.Constant) and node.args[1].value=='Public FIS explicit close left an active FD owner before quiescent GC'):
            node.args[0]=ast.parse('fd_bank(fd_roots,io_owner)',mode='eval').body;changes.append('observe actual live FD owner')
        if isinstance(node,ast.keyword) and node.arg=='non_null_cells' and isinstance(node.value,ast.Constant) and node.value.value==0:
            node.value=ast.parse('sum(bool(oop) for oop in fd_roots)',mode='eval').body;changes.append('FD physical non-null count')
        if isinstance(node,ast.keyword) and node.arg=='compact_vector_sha256':node.arg='ASM_snapshot_vector_sha256'
    [index]=[i for i,node in enumerate(collection.body) if isinstance(node,ast.Assign) and
        len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='vector']
    collection.body[index]=ast.parse('vector=native_roots_collect_snapshot(image,values,images_file,collections)').body[0]
    for node in ast.walk(collection):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='collect':
            S.check(ast.unparse(node.args[2])=='len(compact)','Frozen Parker collect count changed')
            node.args[2]=ast.parse('len(vector)',mode='eval').body;changes.append('native snapshot buffer is the actual collector input')
    [index]=[i for i,node in enumerate(collection.body) if isinstance(node,ast.AugAssign) and
        isinstance(node.target,ast.Name) and node.target.id=='values' and 'roots' in ast.unparse(node.value)]
    collection.body.insert(index,ast.parse('values += [oop for oop in fd_roots if oop]').body[0]);changes.append('include real FD values in independent observer')
    [index]=[i for i,node in enumerate(fn.body) if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and
        isinstance(node.value.func,ast.Attribute) and node.value.func.attr=='check' and len(node.value.args)==2 and
        isinstance(node.value.args[1],ast.Constant) and node.value.args[1].value=='Published gate roots failed to retain private normal Objects']
    fn.body.insert(index+1,ast.parse('io_owner.verify_and_close(heap,contains)').body[0]);changes.append('read then original close after rooted collection')
    fn.body.append(ast.parse("S.check(not contains(heap,io_owner.fd) and not contains(heap,io_owner.stream),'Closed native FD/FIS graph remained rooted')").body[0])
    fn.body.append(ast.parse("result.update(ASM_native_root_snapshots=list(SNAPSHOTS),live_original_FD_graph_retained_then_reclaimed=True)").body[0])
    ast.fix_missing_locations(tree);namespace=dict(vars(K))
    namespace.update(LiveIO=LiveIO,fd_bank=fd_bank,native_roots_collect_snapshot=snapshot,SNAPSHOTS=SNAPSHOTS)
    exec(compile(tree,str(Path(__file__)),'exec'),namespace)
    S.check(len(changes)==6,'Unexpected native root AST adaptation scope')
    return namespace['semantics'],dict(original_tool=S.artifact(Path(K.__file__)),
        original_AST_sha256=hashlib.sha256(ast.dump(ast.parse(original),include_attributes=False).encode()).hexdigest(),
        adapted_AST_sha256=hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest(),changes=changes),ast.unparse(tree)+'\n'


def build(park_result,output):
    accepted=S.read(park_result)
    S.check(accepted['verified'] and accepted['all_park_semantics_completed'] and accepted['JDK_oracle'],
        'Completed original-Java Parker/IO execution required')
    original_images=S.checked(accepted['images']);original=S.read(original_images)
    S.check(original['park_test_generator']==S.artifact(Path(K.__file__)),'Accepted Parker test tool changed')
    for row in original['link_inputs']:S.check(S.artifact(row['path'])==row,'Accepted source link input changed')
    output=output.resolve();S.check(output.is_relative_to(S.ART) and not output.exists(),'Fresh native root consumer output required')
    output.mkdir(parents=True);proofs=[]
    candidate_files=[S.checked(original['accepted_inputs']['candidate']),S.checked(original['park_candidate'])]
    for path in candidate_files:
        candidate=S.read(path);meta=candidate['metadata']['source']
        projection=dict(exports=candidate['exports'],assembly=candidate['assembly'],object=candidate['object'],native_root_spans=meta['native_root_spans'])
        physical=N.provider_projection(projection,meta);proofs+=physical
    S.check([(r['symbol'],r['count']) for r in proofs]==[('boom_file_input_owner_roots',4096),('boom_unsafe_park_gate_roots',16384)],
        'Expected physically verified owned-FD and private-Parker root spans')
    lines=S.checked(original['link_response']).read_text().splitlines()
    consumer,imports=N.complete_consumer_assembly(proofs,source_exports=
        {line.removeprefix('/EXPORT:') for line in lines if line.startswith('/EXPORT:')})
    text='option casemap:none\n'+consumer+KERNEL.read_text()+'\nEND\n'
    asm=output/'native-root-consumer.asm';obj=asm.with_suffix('.obj');asm.write_text(text)
    assembler=Path(S.read(candidate_files[1])['assembler']['path'])
    with obj.with_suffix('.log').open('wb') as log:
        subprocess.run([assembler,'/nologo','/c','/Fo'+str(obj),asm],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
    expected_imports=imports|{name for pair in BASE_SPANS for name in pair}
    S.check(K.B.A.coff_symbols(obj,set())==(EXPORTED,expected_imports),'Actual ASM root consumer COFF contract differs')
    dll=output/'native-root-source-image.dll';rsp=output/'link.rsp';lines=S.checked(original['link_response']).read_text().splitlines()
    exports={line.removeprefix('/EXPORT:') for line in lines if line.startswith('/EXPORT:')}|EXPORTED
    rsp.write_text('\n'.join([line for line in lines if not line.startswith(('/OUT:','/EXPORT:'))]+['"'+str(obj)+'"',
        '/OUT:"'+str(dll)+'"',*['/EXPORT:'+name for name in sorted(exports)]])+'\n')
    with (output/'link.log').open('wb') as log:
        subprocess.run([assembler.with_name('link.exe'),'@'+str(rsp)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=240)
    _,reuse,source=adapted_semantics();script=output/'native-root-semantics.py';script.write_text(source)
    config=json.loads(json.dumps(original));config.update(image=S.artifact(dll),link_response=S.artifact(rsp),
        link_inputs=original['link_inputs']+[S.artifact(obj)],root_consumer=dict(generator=S.artifact(Path(__file__)),helper=S.artifact(Path(N.__file__)),
            kernel=S.artifact(KERNEL),assembly=S.artifact(asm),object=S.artifact(obj),physical_native_spans=proofs,
            base_spans=BASE_SPANS,semantics_reuse=reuse,adapted_semantics=S.artifact(script),
            original_Java_native_provider_runtime_COFF_unchanged=True,formal_provider_registration=False,automatic_GC=False),
        accepted_Parker_execution=S.artifact(park_result),accepted_Parker_images=S.artifact(original_images))
    path=output/'images.json';S.write(path,config);return path


def worker(images,kind):
    config=S.read(images);record=config['root_consumer']
    for path,key in [(Path(__file__),'generator'),(Path(N.__file__),'helper'),(KERNEL,'kernel')]:
        S.check(S.artifact(path)==record[key],'Native root consumer input changed: '+key)
    semantics,reuse,text=adapted_semantics()
    S.check(reuse==record['semantics_reuse'] and S.checked(record['adapted_semantics']).read_text()==text,'Frozen source test AST reuse changed')
    for row in record['physical_native_spans']:
        [fresh]=N.verify_object(S.checked(row['object']),[{k:row[k] for k in ('symbol','count','kind')}],assembly=S.checked(row['assembly']))
        S.check(row==fresh,'Physical native root proof changed')
    K.semantics=semantics;result=K.worker(images,kind)
    S.check(result['verified'] and len(result['real_Java_park'].get('ASM_native_root_snapshots',[]))==2,
        'Original Java source/native ASM root consumer suite failed')
    result.update(scope='explicit_quiescent_ASM_consumer_of_all_normal_primordial_IO_and_Parker_roots',
        game_logic_in_Python=False,automatic_GC=False,formal_provider_registration=False)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--park-result',type=Path)
    parser.add_argument('--images',type=Path);parser.add_argument('--worker',choices=('string','file'))
    parser.add_argument('--output',type=Path,default=S.ART/'provider-native-roots/execution'/uuid4().hex)
    args=parser.parse_args()
    if args.worker:
        images=args.images.resolve();path=images.parent/(args.worker+'-park-execution.json');S.write(path,worker(images,args.worker));print(path)
    else:
        images=args.images.resolve() if args.images else build(args.park_result.resolve(),args.output)
        records=[]
        for kind in ('string','file'):
            with (images.parent/(kind+'-worker.log')).open('wb') as log:
                child=subprocess.run([sys.executable,Path(__file__),'--images',images,'--worker',kind],stdout=log,stderr=subprocess.STDOUT,check=False,timeout=300)
            S.check(child.returncode==0,'Native root source worker failed: '+str(images.parent/(kind+'-worker.log')))
            records.append(S.artifact(images.parent/(kind+'-park-execution.json')))
        oracle=K.compare_oracle(images,records)
        result=dict(verified=True,scope='physical_native_root_spans_and_real_source_quiescent_ASM_snapshot_consumer',
            images=S.artifact(images),cold_process_results=records,JDK_oracle=oracle,normal_source_spans=9,primordial_roots_included=True,
            native_root_cells=[4096,16384],automatic_GC=False,formal_provider_registration=False,game_started=False)
        path=images.parent/'result.json';S.write(path,result);print(path)
