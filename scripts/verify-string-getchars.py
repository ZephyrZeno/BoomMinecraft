"""Check getChars guard order and exact original Code in generated holders."""
import hashlib,json,sys
from pathlib import Path
helper=Path(__file__).with_name('verify-literal-regex.py');prefix=helper.read_text(encoding='utf-8').split('\np=load(sys.argv[1]);',1)[0]
ns={'__file__':str(helper)};exec(compile(prefix,str(helper),'exec'),ns)
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def sha(raw):return hashlib.sha256(raw).hexdigest()
p=load(sys.argv[1]);base_path=Path(sys.argv[2]);base=load(base_path);origin=base['classes']['java.lang.String'];raw=(base_path.parent/'image/java.base/java/lang/String.class').read_bytes();assert sha(raw)==origin['sha256']
c=ns['original'](raw);cp=c['constants'];m=next(m for m in c['methods'] if m[1:3]==('getChars','(II[CI)V'));body,tail=ns['code'](m)
assert m[0]==1 and body[:4]==bytes.fromhex('1b1c2ab6') and body[9:17]==bytes.fromhex('15041c1b642dbeb8') and body[19]==0x57
def member(index):
 tag,ref=cp[index];nt=cp[ref[1]][1];return tag,cp[cp[ref[0]][1]][1],cp[nt[0]][1],cp[nt[1]][1]
assert member(int.from_bytes(body[4:6],'big'))==(10,'java/lang/String','length','()I')
bindings=p['string_getchars'];assert bindings and not p['full_game_ready']
pre_origin=base['classes']['jdk.internal.util.Preconditions'];pre_raw=(base_path.parent/'image/java.base/jdk/internal/util/Preconditions.class').read_bytes();assert sha(pre_raw)==pre_origin['sha256']
pre=ns['original'](pre_raw)
for binding in bindings:
 assert binding['string_origin']==origin and binding['code_sha256']==sha(body) and not binding['original_range_guard_bodies_executed'] and not binding['original_get_chars_body_executed']
 assert binding['native_source_sha256']==sha(Path('native/runtime/strings.asm').read_bytes())
 assert binding['preconditions_origin']==pre_origin
 for digest,at in zip(binding['guard_code_sha256'],[7,17]):
  _,owner,name,desc=member(int.from_bytes(body[at:at+2],'big'));assert owner=='java/lang/String' and name in ('checkBoundsBeginEnd','checkBoundsOffCount')
  original=next(m for m in c['methods'] if m[1:3]==(name,desc))
  assert sha(ns['code'](original)[0])==digest
 for name,digest in zip(['checkFromToIndex','checkFromIndexSize'],binding['preconditions_code_sha256']):
  original=next(m for m in pre['methods'] if m[1:3]==(name,'(IIILjava/util/function/BiFunction;)I'))
  assert original[0]==9 and sha(ns['code'](original)[0])==digest
print(json.dumps(dict(passed=True,call_sites=len(bindings),source_range_guards_verified=True,guards_and_copy_in_ASM=True,original_String_getChars_body_executed=False)))
