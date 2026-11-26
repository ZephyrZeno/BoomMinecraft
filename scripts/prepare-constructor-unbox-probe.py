"""Select original primitive wrapper layouts for a development unboxing probe."""
import argparse
import importlib.util
import json
from pathlib import Path


spec=importlib.util.spec_from_file_location('unbox_source_identity',Path(__file__).with_name('runtime-provider-source.py'))
S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    baseline=a.baseline.resolve();output=a.output.resolve()
    S.check(baseline.is_relative_to(S.ART) and output.is_relative_to(S.ART),'Unboxing fixture must remain in project .boom')
    closure=S.read(baseline/'closure.json');proof=S.read(baseline/'selection-verification.json')
    S.check(proof['verified'] and proof['diagnostic_only'],'Unboxing source fixture requires a verified diagnostic baseline')
    identity,summary,classes=S.base(closure['batch'],closure['plan'])
    S.check(closure['source_batch_summary_sha256']==identity['batch_summary']['digest']['sha256'],'Unboxing baseline source batch changed')
    names={(c['origin']['loader'],c['name']):c['id'] for c in classes}
    specs=list(zip(('Boolean','Byte','Character','Short','Integer','Long','Float','Double'),'ZBCSIJFD',(1,1,2,2,4,8,4,8)))
    wanted={names['bootstrap','java/lang/'+name] for name,_,_ in specs};layouts={}
    layout_path=S.checked(summary['layouts'])
    with layout_path.open(encoding='utf-8') as stream:
        for line in stream:
            row=json.loads(line)
            if row['class_id'] in wanted:layouts[row['class_id']]=row
    boxes=[]
    for kind,(name,descriptor,width) in enumerate(specs):
        id_=names['bootstrap','java/lang/'+name];row=layouts[id_]
        S.check(row['candidate'] is not None and row['diagnostic'] is None,'Original wrapper layout unavailable')
        fields=[f for f in row['candidate']['fields'] if f['member']['owner']==id_ and f['member']['name']=='value' and f['member']['descriptor']==descriptor]
        S.check(len(fields)==1 and fields[0]['storage_bytes']==width,'Original wrapper value field differs')
        boxes.append(dict(class_id=id_,kind=kind,offset=fields[0]['offset'],width=width,payload_bytes=row['candidate']['payload_bytes'],source_sha256=classes[id_]['origin']['sha256']))
    S.write(output,dict(base=identity,boxes=boxes,object_class=names['bootstrap','java/lang/Object'],
        fixture_objects_only=True,Java_wrapper_constructors_executed=False,game_started=False))
