"""Build and verify a fresh diagnostic image for the original JDK wait/catch/join regression."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OWNERS={'java/lang/Object','java/lang/Thread','java/lang/Throwable','java/lang/Exception','java/lang/InterruptedException',
        'java/io/InterruptedIOException','java/io/IOException','java/io/PipedInputStream','java/lang/ref/Reference',
        'java/lang/StackTraceElement','java/lang/Thread$FieldHolder','java/util/TimerThread','java/util/TaskQueue'}
METHODS={'<init>','<clinit>','fillInStackTrace','getAndClearInterrupt','wait','interrupt','isVirtual','awaitSpace',
         'checkStateForReceive','getStackTraceDepth','getOurStackTrace','start','join','isAlive','alive','run','runWith',
         'exit','clearReferences','threadContainer','dispatchUncaughtException','mainLoop','isEmpty','clear'}
ROOTS=('java/io/PipedInputStream','java/lang/Thread','java/lang/Object','java/lang/InterruptedException',
       'java/io/InterruptedIOException','java/util/TimerThread','java/util/TaskQueue')
ENTRIES=(('java/io/PipedInputStream','awaitSpace'),('java/lang/Object','wait'),('java/lang/Thread','interrupt'),
         ('java/lang/Thread','start'),('java/lang/Thread','join'),('java/lang/InterruptedException','<init>'))


def execute(argv,path,timeout):
    with path.open('xb') as log:
        r=subprocess.run(list(map(str,argv)),cwd=ROOT,stdout=log,stderr=log,timeout=timeout)
    if r.returncode:
        raise RuntimeError(f'{path} (exit {r.returncode})\n'+path.read_text(errors='replace')[-1800:])


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('batch','plan','runtime','providers'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--output',type=Path,default=ROOT/'.boom/diagnostic-startup'/('original-monitor-wait-'+uuid.uuid4().hex))
    a=p.parse_args()
    directory=a.output.resolve()
    if not directory.is_relative_to(ROOT/'.boom') or directory.exists():
        p.error('An unused directory under .boom is required')
    directory.mkdir(parents=True)
    print(directory,flush=True)
    batch,plan,runtime=a.batch.resolve(),a.plan.resolve(),a.runtime.resolve()
    classes=set()
    with (plan/'classes.jsonl').open(encoding='utf8') as stream:
        for line in stream:
            c=json.loads(line)
            if c['origin']['loader']=='bootstrap' and c['name'] in OWNERS:
                classes.add(c['id'])
    methods=[]
    with (plan/'methods.jsonl').open(encoding='utf8') as stream:
        for line in stream:
            m=json.loads(line)
            if m['class_id'] in classes and m['symbol']['name'] in METHODS and m.get('code_sha256'):
                methods.append(m['id'])
    profile=directory/'source-profile.json'
    profile.write_text(json.dumps(dict(source_batch_summary_sha256=hashlib.sha256((batch/'summary.json').read_bytes()).hexdigest(),
                                       admitted_methods=sorted(methods),admitted_classes=sorted(classes))),encoding='utf-8')
    packs=json.loads(a.providers.read_bytes())
    stage=directory/'image'
    execute([sys.executable,ROOT/'scripts/prepare-diagnostic-closure.py',batch,'--plan',plan,'--output',stage,
             '--runtime',runtime/'boom-runtime.dll','--admit-profile',profile,
             *(x for n in ROOTS for x in ('--class-root','bootstrap:'+n)),
             *(x for cls,n in ENTRIES for x in ('--entry',f'bootstrap:{cls}:{n}:()V')),
             *(x for pack in packs for x in ('--provider-pack',pack))],directory/'selection.log',1200)
    execute([sys.executable,ROOT/'scripts/build-diagnostic-closure.py',
             '--batch',batch,'--plan',plan,'--runtime',runtime,'--output',stage,'--prepared-selection'],directory/'link-verify.log',1200)
    execute([sys.executable,'-u',HERE/'test_framed.py','--runtime',runtime,'--selection',stage,
             '--output',directory/'result.json'],directory/'execution.log',45)
    print((directory/'result.json').read_text(),flush=True)
