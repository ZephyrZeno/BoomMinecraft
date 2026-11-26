import copy
import importlib.util
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location('normal_Class_verifier',Path(__file__).resolve().parents[1]/'scripts/verify-batch-classes.py')
V=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(V)


class NormalClassSourceTests(unittest.TestCase):
    def model(self):
        def c(id_,name,loader='bootstrap',source='jdk:java.base',flags=0x21):
            return dict(id=id_,name=name,access=flags,superclass='' if id_==0 else 'java/lang/Object',fields=[],origin=dict(loader=loader,source_id=source,sha256=str(id_),java_class_major=65))
        classes=[c(0,'java/lang/Object'),c(1,'java/lang/Class',flags=0x31),c(2,'java/lang/ClassLoader',flags=0x421),c(3,'java/lang/Module',flags=0x31),
                 c(4,'java/sql/Connection','platform','jdk:java.sql',0x601),c(5,'p/Value','vanilla-application','library:example')]
        layouts={}
        for owner,fields in ((classes[1],[('classLoader','Ljava/lang/ClassLoader;',0x12),('module','Ljava/lang/Module;',0x82),('componentType','Ljava/lang/Class;',0x12),('name','Ljava/lang/String;',0x82)]),
                             (classes[3],[('loader','Ljava/lang/ClassLoader;',0x12)])):
            owner['fields']=[dict(name=n,descriptor=d,access=a) for n,d,a in fields]
            slots=[dict(member=dict(owner=owner['id'],index=i,**f),offset=i*8,reference=True,storage_bytes=8) for i,f in enumerate(owner['fields'])]
            layouts[owner['id']]=dict(payload_bytes=len(slots)*8,reference_prefix=len(slots),fields=slots)
        types={c['id']:dict(id=c['id'],kind=2 if c['access']&0x200 else 1,parent_component=None if c['id']==0 else 0,defining_loader=c['origin']['loader'],name=c['name']) for c in classes}
        types[6]=dict(id=6,kind=0,parent_component=None,defining_loader='bootstrap',name='I')
        for id_,component,name in ((7,5,'[Lp/Value;'),(8,7,'[[Lp/Value;')):types[id_]=dict(id=id_,kind=3,parent_component=component,defining_loader='vanilla-application',name=name)
        return classes,layouts,types

    def test_normal_fields_are_from_original_Class_and_Module(self):
        classes,layouts,_=self.model();shape=V.shape_model(classes,layouts)
        self.assertEqual((shape['loader_offset'],shape['module_offset'],shape['component_offset']),(0,8,16))
        for mutation in ('source','access','physical'):
            c,l=copy.deepcopy(classes),copy.deepcopy(layouts)
            if mutation=='source':c[1]['origin']['source_id']='replacement'
            elif mutation=='access':c[1]['fields'][0]['access']=2
            else:l[1]['fields'][0]['reference']=False
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):V.shape_model(c,l)

    def test_loader_module_and_multidimensional_component_identities(self):
        classes,_,types=self.model();loaders,modules,rows=V.identities(classes,types)
        self.assertEqual(loaders,['bootstrap','platform','vanilla-application'])
        self.assertEqual(modules[0],dict(id=0,name='java.base',loader=0))
        self.assertEqual((rows[6]['loader'],rows[6]['module'],rows[6]['flags']),(0,0,1))
        self.assertEqual((rows[7]['loader'],rows[8]['loader']),(2,2))
        self.assertEqual(rows[7]['module'],rows[5]['module'])
        self.assertEqual((rows[7]['component'],rows[8]['component']),(5,7))
        self.assertIsNone(rows[4]['superclass'])

    def test_wrong_array_defining_loader_is_not_replaced_by_bootstrap(self):
        classes,_,types=self.model();types[8]['defining_loader']='bootstrap'
        with self.assertRaisesRegex(ValueError,'defining loader'):V.identities(classes,types)

    def test_literal_and_native_instance_queries_do_not_fake_class_initialization(self):
        self.assertIn('mov r8d,0\n jmp boom_java_class_load',V.literal_body('boom_batch_literal_load_1_2',0))
        for _,name,_,access,op in V.SPECS:
            self.assertFalse(access&8);self.assertNotIn('class_ensure',V.native_body(7,op));self.assertNotEqual(name,'registerNatives')

    def test_pool_rows_preserve_zero_parent_and_strong_root_regions(self):
        classes,layouts,types=self.model();shape=V.shape_model(classes,layouts);loaders,modules,rows=V.identities(classes,types)
        body=V.pool_body(shape,9,loaders,modules,rows,32)
        self.assertIn('boom_java_class_roots LABEL QWORD\n QWORD 9 DUP(?)',body)
        self.assertIn('DWORD 4294967295,0,',body)
        self.assertIn('boom_java_class_pool DWORD 04A434C53h,1,0,9',body)

    def test_names_preserve_arrays_primitives_unicode_and_loader_duplicates(self):
        types={0:dict(kind=0,name='I'),1:dict(kind=1,name='p/名'),2:dict(kind=3,name='[[Lp/名;'),3:dict(kind=1,name='p/名')}
        names,canonical=V.names_model(types)
        def text(i):return bytes(b for u in canonical[names[i]['canonical']]['utf16'] for b in (u&255,u>>8)).decode('utf-16-le')
        self.assertEqual([text(i) for i in range(4)],['int','p.名','[[Lp.名;','p.名'])
        self.assertEqual(names[1]['canonical'],names[3]['canonical'])

    def test_name_interning_reuses_literal_zero_and_keeps_hash_collisions_distinct(self):
        types={0:dict(kind=0,name='I'),1:dict(kind=1,name='Aa'),2:dict(kind=1,name='BB')}
        names,canonical=V.names_model(types,{tuple(map(ord,'int')):0})
        self.assertEqual(canonical[names[0]['canonical']]['literal'],0)
        self.assertNotEqual(names[1]['canonical'],names[2]['canonical'])
        self.assertEqual(canonical[names[1]['canonical']]['java_hash'],canonical[names[2]['canonical']]['java_hash'])

if __name__=='__main__':unittest.main()
