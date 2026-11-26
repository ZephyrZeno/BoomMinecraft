"""Independently verify storage/source binding and emitted VM type aliases."""
import hashlib,json,runpy,sys
from pathlib import Path
parse=runpy.run_path(str(Path(__file__).with_name('verify-jdk-bridges.py')))['parse']
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
p=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'));base=Path(sys.argv[2]);jdk=json.loads(base.read_text(encoding='utf-8-sig'))
plan=p['string_lowercase'];assert p['schema']==62 and not p['full_game_ready'] and plan['abi']==1
assert not plan['original_java_string_method_executed'] and not plan['dictionary_sigma_implemented'] and not plan['dynamic_locale_providers'] and not plan['automatic_gc']
for field,name in [('string_origin','java.lang.String'),('locale_origin','java.util.Locale'),('base_origin','sun.util.locale.BaseLocale')]:
    assert plan[field]==jdk['classes'][name]
    raw=base.parent/'image/java.base'/Path(name.replace('.','/')+'.class');assert sha(raw)==plan[field]['sha256']
for key,name in [('base_offset','baseLocale'),('language_offset','language')]:
    layout=plan['locale_layout' if name=='baseLocale' else 'base_layout'];f=next(f for f in layout['fields'] if f['name']==name)
    assert layout['abi']==2 and f['storage_bytes']==8 and f['offset']==plan[key] and f['offset']<layout['reference_prefix_fields']*8
for tag,type_key,layout_key in [('boom_lower_locale_layout','locale_type','locale_layout'),('boom_lower_base_layout','base_type','base_layout')]:
    row=next(r for r in p['runtime_type_bindings'] if r['tag']=='OFFSET '+tag)
    assert row['type_id']==plan[type_key] and row['payload_bytes']==plan[layout_key]['payload_bytes'] and row['references']==plan[layout_key]['reference_prefix_fields']
    assert p['mirror_types'][row['type_id']]['key']['loader']=='bootstrap'
assert sha('native/runtime/string_lowercase.asm')==plan['native_source_sha256']
w=plan['words'];assert w['image_sha256']==jdk['image']['digest']['sha256'] and not w['dictionary_word_boundaries'] and not w['dynamic_locale_providers']
assert sha('native/runtime/word_break.asm')==w['native_source_sha256'] and sha('native/runtime/unicode_context.asm')==w['context_source_sha256']
assert w['categories']==22 and len(w['ends'])==20 and len(w['states'])==440
assert any(a>>8==b>>8 for a,b in zip(w['supplementary'],w['supplementary'][1:]))
assert plan['bindings'] and all(b['caller']['source_id']=='explicit:dev.boom.lowercase.LowercaseProgram' or b['caller']['loader']=='explicit-application' for b in plan['bindings'])
assert not any(s['class_name'] in ('java/util/Locale','sun/util/locale/BaseLocale') and s['method']=='<clinit>' for s in p['symbols'])
print(json.dumps(dict(passed=True,source_bound_String_method=True,Locale_layout_is_VM_fixture=True,
                     original_String_and_Locale_initializers_executed=False,dictionary_Sigma_implemented=False,game_started=False)))
