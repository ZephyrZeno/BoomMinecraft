"""Access flags are not reflection modifiers, particularly for nested arrays."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile
SPEC=importlib.util.spec_from_file_location('class_flags_contract_tests',Path(__file__).resolve().parents[1]/'scripts/class-flags-source.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)

def original_class(header=0x21,inner=None,synthetic=None):
    cp=[]
    def utf(s):
        b=s.encode();cp.append(b'\x01'+struct.pack('>H',len(b))+b);return len(cp)
    def clazz(s):
        i=utf(s);cp.append(b'\x07'+struct.pack('>H',i));return len(cp)
    this=clazz('fixture/Flags$Type');parent=clazz('java/lang/Object');attributes=[]
    if inner is not None:
        name=utf('InnerClasses');attributes.append((name,struct.pack('>HHHHH',1,this,0,0,inner)))
    if synthetic is not None:attributes.append((utf('Synthetic'),synthetic))
    return (struct.pack('>IHHH',0xcafebabe,0,65,len(cp)+1)+b''.join(cp)+
        struct.pack('>HHHHHHH',header,this,parent,0,0,0,len(attributes))+
        b''.join(struct.pack('>HI',n,len(b))+b for n,b in attributes))

class ClassFlagsTests(unittest.TestCase):
    def test_super_bit_is_raw_but_not_a_reflection_modifier(self):
        r=M.original(original_class());self.assertEqual((r['raw_flags'],r['modifiers']),(0x21,1))

    def test_self_inner_access_controls_private_protected_and_static(self):
        for raw,inner in [(0x20,0xa),(0x21,0xc),(0x21,9)]:
            with self.subTest(inner=inner):
                r=M.original(original_class(raw,inner));self.assertEqual((r['raw_flags'],r['modifiers']),(raw,inner))

    def test_old_synthetic_attribute_is_preserved_and_checked(self):
        r=M.original(original_class(synthetic=b''));self.assertEqual((r['raw_flags'],r['modifiers']),(0x1021,0x1001))
        with self.assertRaisesRegex(ValueError,'Synthetic'):M.original(original_class(synthetic=b'\0'))

    def test_inner_flags_override_outer_header_even_for_interfaces(self):
        r=M.original(original_class(0x600,0x608));self.assertEqual(r['modifiers'],0x608)

    def test_arrays_inherit_bottom_visibility_but_raw_flags_stay_zero(self):
        raw=original_class(0x20,0xa)
        classes=[dict(id=0,name='fixture/Flags$Type',access=0x20,parse_error=None,origin=dict(loader='bootstrap',sha256=hashlib.sha256(raw).hexdigest()))]
        rows=[dict(id=0,kind=1),dict(id=1,kind=0),dict(id=2,kind=3,parent_component=0),
              dict(id=3,kind=3,parent_component=2),dict(id=4,kind=3,parent_component=1)]
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'types.zip'
            with zipfile.ZipFile(p,'w') as z:z.writestr('types.jsonl','\n'.join(map(json.dumps,rows)))
            catalog=Path(d)/'catalog.json'
            catalog.write_text(json.dumps(dict(image=dict(path=str(Path(d)/'jdk/lib/modules')),classes={})),encoding='utf-8')
            summary=dict(frames=dict(original_system_catalog=dict(path=str(catalog),digest=dict(
                size=catalog.stat().st_size,sha256=hashlib.sha256(catalog.read_bytes()).hexdigest()))),
                runtime_metadata=dict(type_capacity=6,index=dict(path=str(p),digest=dict(size=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))))
            # Supply the two declaration names without adding runtime types.
            classes+= [dict(id=10,name='java/lang/Class',origin=dict(loader='bootstrap')),dict(id=11,name='jdk/internal/reflect/Reflection',origin=dict(loader='bootstrap'))]
            with patch.object(M.C.RawClasses,'read',return_value=raw):result=M.index(summary,classes)
        self.assertEqual([(r['raw_flags'],r['modifiers'],r['state']) for r in result['rows']],
            [(0x20,0xa,1),(0x411,0x411,1),(0,0x412,1),(0,0x412,1),(0,0x411,1),(0,0,0)])

if __name__=='__main__':unittest.main()
