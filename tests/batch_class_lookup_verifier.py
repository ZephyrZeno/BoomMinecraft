"""Lookup rules must retain loader, native-source and initialization identity."""
import copy
import importlib.util
from pathlib import Path
import unittest

S=importlib.util.spec_from_file_location('class_lookup_contract',Path(__file__).resolve().parents[1]/'scripts/verify-batch-class-lookup.py');M=importlib.util.module_from_spec(S);S.loader.exec_module(M)
class LookupContractTests(unittest.TestCase):
    def fixture(self):
        classes=[];inventory={}
        for i,(owner,name,desc,op) in enumerate(M.SPECS):
            classes.append(dict(id=i,name=owner,origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256=str(i),generated=None),method_ids=[10+i]))
            inventory[10+i]=(i,name,desc,str(i),None,None,None,None,0x10a)
        for i,(name,loader) in enumerate([('p/Aa','bootstrap'),('p/BB','bootstrap'),('p/Aa','vanilla-application'),('p/中文','bootstrap')],2):
            classes.append(dict(id=i,name=name,origin=dict(loader=loader,source_id='jdk:java.base',sha256=str(i),generated=None),method_ids=[]))
        types=[dict(id=c['id'],name=c['name'],kind=1,defining_loader=c['origin']['loader']) for c in classes]
        types.extend([dict(id=6,name='[[I',kind=3,defining_loader='bootstrap'),dict(id=7,name='[Lp/Aa;',kind=3,defining_loader='bootstrap')])
        states=[dict(class_id=c['id'],source_sha256=str(c['id']),diagnostic=None) for c in classes]
        return classes,inventory,types,states
    def test_hash_collision_keeps_both_exact_names(self):
        methods,names,inits,count=M.contract(*self.fixture());a=next(n for n in names if n['type_id']==2);b=next(n for n in names if n['type_id']==3)
        self.assertEqual(a['java_hash'],b['java_hash']);self.assertNotEqual(a['utf16'],b['utf16']);self.assertNotIn(4,[n['type_id'] for n in names]);self.assertEqual(len(methods),2)
    def test_unknown_layout_is_retained_as_unavailable(self):
        c,i,t,s=self.fixture();t=[v for v in t if v['id']!=2];_,n,init,_=M.contract(c,i,t,s)
        self.assertEqual(next(v for v in n if v['type_id']==2)['flags'],0);self.assertNotIn(2,[v['class_id'] for v in init])
    def test_source_native_and_original_owner_required(self):
        for change in ('code','flags','owner'):
            with self.subTest(change=change):
                c,i,t,s=self.fixture()
                if change=='owner':c[0]['origin']['source_id']='other'
                else:
                    row=list(i[10]);row[4 if change=='code' else 8]='code' if change=='code' else 0x108;i[10]=tuple(row)
                with self.assertRaises(ValueError):M.contract(c,i,t,s)
    def test_projection_preserves_unselected_initialization_request(self):
        full=M.initialization_map(4,{1,2});projected=M.initialization_map(4,{1,2},{1})
        self.assertIn('QWORD OFFSET boom_class2,0',full);self.assertIn('QWORD 0,OFFSET boom_batch_initialize_2',projected);self.assertNotIn('OFFSET boom_class2',projected)
    def test_arrays_are_lookup_types_without_class_initializers(self):
        _,names,inits,_=M.contract(*self.fixture());self.assertEqual([n['flags'] for n in names if n['type_id'] in (6,7)],[3,3]);self.assertNotIn(6,[r['class_id'] for r in inits])
    def test_unavailable_source_state_is_not_an_initializer(self):
        c,i,t,s=self.fixture();s[2]['diagnostic']='unprovided';_,_,inits,_=M.contract(c,i,t,s);self.assertNotIn(2,[r['class_id'] for r in inits])
    def test_interfaces_are_normal_named_initialization_targets(self):
        c,i,t,s=self.fixture();t[2]['kind']=2;_,names,inits,_=M.contract(c,i,t,s)
        self.assertEqual(next(n for n in names if n['type_id']==2)['flags'],1);self.assertIn(2,[r['class_id'] for r in inits])
if __name__=='__main__':unittest.main()
