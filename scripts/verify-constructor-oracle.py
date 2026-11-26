"""Compare the translated-image fixture's original metadata with independent JVM."""
import argparse
import base64
import json
from pathlib import Path

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('oracle',type=Path);a=p.parse_args()
    s=json.loads(a.source.read_text());seen={};counts={}
    for line in a.oracle.read_text(encoding='utf-8-sig').splitlines():
        row=line.split('\t');i=int(row[1])
        if row[0]=='TYPE':counts[i]=(row[2],int(row[3]),int(row[4]))
        else:
            assert row[0]=='CTOR' and len(row)==8
            key=(i,row[2]);assert key not in seen
            seen[key]=dict(modifiers=int(row[3]),signature=None if row[4]=='-' else base64.b64decode(row[4]).decode('utf-8'),
                annotations='' if row[5]=='-' else row[5],parameter_annotations='' if row[6]=='-' else row[6],
                exception_names=[] if row[7]=='' else row[7].split(','))
    expected={}
    for i,c in enumerate(s['cases']):
        assert counts[i]==(c['name'],len(c['constructors']),sum(bool(r['modifiers']&1) for r in c['constructors']))
        for r in c['constructors']:
            expected[i,r['descriptor']]={k:r[k] for k in ('modifiers','signature','annotations','parameter_annotations','exception_names')}
    assert expected==seen,'Independent JVM constructor metadata differs'
    scope='original_JDK_and_vanilla_application_constructor_metadata_only' if any(c.get('original_application_class') for c in s['cases']) else 'original_JDK_constructor_metadata_only'
    print(json.dumps(dict(verified=True,cases=len(counts),constructors=len(seen),scope=scope,game_started=False)))
