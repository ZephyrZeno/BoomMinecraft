"""Locked normal field IDs required by WindowsNativeDispatcher.initIDs on JDK 21."""
import json
import zipfile


OWNER='sun/nio/fs/WindowsNativeDispatcher'
S='Ljava/lang/String;'
GROUPS={
    'FirstFile':[('handle','J'),('name',S),('attributes','I')],
    'FirstStream':[('handle','J'),('name',S)],
    'VolumeInformation':[('fileSystemName',S),('volumeName',S),('volumeSerialNumber','I'),('flags','I')],
    'DiskFreeSpace':[(n,'J') for n in ('freeBytesAvailable','totalNumberOfBytes','totalNumberOfFreeBytes','bytesPerSector')],
    'Account':[('domain',S),('name',S),('use','I')], 'AclInformation':[('aceCount','I')],
    'CompletionStatus':[('error','I'),('bytesTransferred','I'),('completionKey','J')]}
OWNERS=[OWNER+'$'+n for n in GROUPS]


def index(summary,plan,classes,source):
    owners={classes[n]['id']:classes[n] for n in OWNERS}
    layout={}
    with source.checked(summary['layouts']).open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['class_id'] in owners:
                layout[row['class_id']]=row
    first_field={}
    count=0
    with source.checked(plan['artifacts']['classes']).open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['id'] in owners:
                first_field[row['id']]=count
            count+=len(row['fields'])
    fields=source.module('nio_native_field_contracts','file-bootstrap-source.py')
    rows=[]
    for suffix,specs in GROUPS.items():
        cls=classes[OWNER+'$'+suffix]
        source.check(cls['access']==0x20 and cls['origin']['source_id']=='jdk:java.base' and not cls['origin'].get('generated'),
                     'Original Windows dispatcher nested class identity differs')
        raw=source.original_class(summary,cls)
        source.check(raw[:4]==bytes.fromhex('cafebabe'),'Locked Windows dispatcher class is missing')
        descriptions=[(n,d,2,4 if d=='I' else 8,d==S) for n,d in specs]
        checked=fields.fields(cls,layout[cls['id']],descriptions,source)
        for field in checked:
            idx=next(i for i,f in enumerate(cls['fields']) if f['name']==field['name'] and f['descriptor']==field['descriptor'])
            rows.append(dict(**field,index=idx,class_id=cls['id'],map_id=first_field[cls['id']]+idx,
                             reference=field['descriptor']==S,source_sha256=cls['origin']['sha256']))
    wanted={f['map_id']:f for f in rows}
    seen=set()
    with zipfile.ZipFile(source.checked(summary['runtime_metadata']['index'])) as z:
        for line in z.open('fields.jsonl'):
            m=json.loads(line)
            if m['id'] not in wanted:
                continue
            f=wanted[m['id']]
            source.check((m['declaring_class'],m['declaring_field'],m['storage_bytes'],m['reference'])==
                         (f['class_id'],f['index'],f['width'],f['reference']) and
                         {x['receiver_class']:x['offset'] for x in m['rows']}.get(f['class_id'])==f['offset'],
                         'Normal JNI field layout/map differs')
            seen.add(m['id'])
    source.check(len(seen)==len(rows)==20,'Windows dispatcher JNI field set is incomplete')
    return rows


def data(rows):
    names=set()
    table=['.const','ALIGN 8','nio_dispatcher_field_rows LABEL BYTE']
    for f in rows:
        symbols=(f"boom_class{f['class_id']}",f"boom_layout{f['class_id']}",f"boom_batch_field_record{f['map_id']}")
        names.update(symbols)
        table.append(' QWORD '+','.join('OFFSET '+s for s in symbols))
        table.append(f" DWORD {f['class_id']},{f['index']},{f['offset']},{f['width']},{int(f['reference'])},0")
    table+=['.data','ALIGN 8','PUBLIC boom_nio_dispatcher_ids_pool','boom_nio_dispatcher_ids_pool DWORD 044494F4Eh,1',
            f' DWORD {len(rows)},48',' QWORD OFFSET nio_dispatcher_field_rows,0']
    return '\n'.join(table)+'\n',names
