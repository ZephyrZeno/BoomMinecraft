"""Select complete verified dispatch tables without inventing receiver pruning."""
import json
import zipfile


def table_source(table):
    id_=table['id'];target=table['array_target'];ptr='0' if target is None else f'OFFSET boom_m{target}'
    body=f".const\nALIGN 8\nPUBLIC boom_batch_vtable{id_}\nboom_batch_vtable{id_} DWORD 056445350h,1,{len(table['rows'])},0\n QWORD OFFSET boom_batch_vrows{id_},{ptr}\n DWORD {table['array_error']},0\nboom_batch_vrows{id_} LABEL BYTE\n"
    for row in table['rows']:
        ptr='0' if row['target'] is None else f"OFFSET boom_m{row['target']}"
        body+=f" DWORD {row['receiver']},{row['error']}\n QWORD {ptr}\n"
    return body


def constraint_source(site):
    d=site['dispatch']
    return f".const\nALIGN 8\nboom_batch_vconstraints_{site['label']} QWORD OFFSET boom_t{d['symbolic_owner']},OFFSET boom_t{d['receiver_constraint']}\n"


class Dispatch:
    def __init__(self,summary,sources):
        self.summary=summary;self.sources=sources;self.sites=None;self.tables=None

    def load(self):
        if self.sites is not None:return
        self.sites={};self.tables={}
        # Keep unselected records as compact JSON bytes. Parsing all row objects
        # permanently would multiply memory on a broad source closure.
        with zipfile.ZipFile(self.summary['index']['path']) as bundle:
            for name,field,index in (('sites.jsonl','label',self.sites),('tables.jsonl','id',self.tables)):
                for line in bundle.open(name):
                    key=json.loads(line)[field]
                    if key in index:raise ValueError('Duplicate source dispatch index entry: '+str(key))
                    index[key]=line

    def site(self,label):
        self.load()
        if label not in self.sites:raise ValueError('Source virtual site is absent: '+label)
        site=json.loads(self.sites[label])
        if site['diagnostic'] is not None or site['table'] is None or site['assembly_unit'] is None:
            raise ValueError('Source virtual site is unavailable: '+str(site['diagnostic']))
        return site

    def table(self,id_):
        self.load()
        if id_ not in self.tables:raise ValueError('Source dispatch table is absent: '+str(id_))
        table=json.loads(self.tables[id_])
        if table['diagnostic'] is not None or table['assembly_unit'] is None:
            raise ValueError('Source dispatch table is unavailable: '+str(table['diagnostic']))
        return table

    def path(self,row):return self.summary['units'][row['assembly_unit']]['assembly']['path']

    def fragment(self,row,body):
        symbol=f"boom_batch_vtable{row['id']}" if 'id' in row else 'boom_batch_vconstraints_'+row['label']
        return self.sources.fragment(self.path(row),symbol,body)
