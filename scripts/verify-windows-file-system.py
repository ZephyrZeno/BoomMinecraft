"""Inspect original field/native declarations; do not claim Java execution."""
import hashlib,json,runpy,sys
from pathlib import Path
helper=runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))
p=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'));plan=p['plan']
assert p['executable_class_ids_are_placeholders'] and not p['original_Java_initializers_executed'] and not p['full_game_ready']
assert plan['abi']==1 and plan['file_initialization_required'] and not plan['automatic_gc']
for field,origin in [('original_file','file_origin'),('original_file_system','origin')]:
    assert plan[origin]['loader']=='bootstrap' and plan[origin]['source_id']=='jdk:java.base'
    assert hashlib.sha256(Path(p[field]).read_bytes()).hexdigest()==plan[origin]['sha256']
c=helper['parse'](Path(p['original_file_system']).read_bytes())
native=next(m for m in c['methods'] if m[1:3]==('initIDs','()V'));assert native[0]==0x10a and not any(n=='Code' for n,_ in native[3])
layout=plan['file_layout'];field=next(f for f in layout['fields'] if f['name']=='path')
assert layout['abi']==2 and field['descriptor']=='Ljava/lang/String;' and field['declaring_class']=='java/io/File'
assert field['storage_bytes']==8 and field['offset']==plan['path_offset'] and field['offset']%8==0
assert field['offset']<layout['reference_prefix_fields']*8 and field['offset']+8<=layout['payload_bytes']
assert plan['bindings'] and all(b['caller']==plan['origin'] for b in plan['bindings'])
assert hashlib.sha256(Path('native/runtime/winnt_file_system.asm').read_bytes()).hexdigest()==plan['native_source_sha256']
print(json.dumps(dict(passed=True,source_native_and_field_layout_checked=True,VM_metadata_fixture=True,original_Java_initializers_executed=False,game_started=False)))
