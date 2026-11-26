"""Independent checks for inheritance, loader identity and physical field plans."""
import importlib.util
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location('metadata_verifier',Path(__file__).resolve().parents[1]/'scripts/verify-batch-metadata.py')
V=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(V)


def source(id_,name,parent='java/lang/Object',loader='bootstrap',flags=1,fields=(),interfaces=()):
    return dict(id=id_,name=name,superclass=parent,interfaces=list(interfaces),access=flags,parse_error=None,
                fields=[dict(name=n,descriptor=d,access=a) for n,d,a in fields],
                origin=dict(loader=loader,source_id='jdk:java.base' if name=='java/lang/Object' else 'fixture',sha256='a'*64))


class MetadataTests(unittest.TestCase):
    def test_inherited_fields_move_without_merging_hidden_fields(self):
        classes=[source(0,'java/lang/Object',''),
                 source(1,'p/Base',fields=[('count','I',1),('ref','Ljava/lang/Object;',1),('wide','J',1),('flag','Z',1)]),
                 source(2,'p/Leaf','p/Base',fields=[('count','I',1),('other','Ljava/lang/Object;',1)])]
        _,ancestors,parents,omitted=V.source_model(classes)
        self.assertEqual(omitted,[]);self.assertEqual(ancestors[2],{0,1,2})
        base,_,_=V.physical_fields(classes,parents,1);leaf,payload,refs=V.physical_fields(classes,parents,2)
        self.assertEqual(next(f['offset'] for f in base if f['name']=='count'),16)
        self.assertEqual([(f['owner'],f['offset']) for f in leaf if f['name']=='count'],[(1,24),(2,28)])
        self.assertEqual((payload,refs),(33,2))

    def test_same_binary_name_does_not_merge_defining_loaders(self):
        classes=[source(0,'java/lang/Object',''),source(1,'p/Same',loader='platform'),
                 source(2,'p/Same',loader='vanilla-application')]
        lookup,_,_,_=V.source_model(classes)
        # Parent delegation chooses platform, while the source identity remains distinct.
        self.assertEqual(lookup('vanilla-application','p/Same'),1)
        self.assertEqual(classes[2]['id'],2)

    def test_incomplete_cycles_and_final_superclasses_remain_unprovided(self):
        classes=[source(0,'java/lang/Object',''),source(1,'p/Missing','p/Absent'),
                 source(2,'p/Child','p/Missing'),source(3,'p/A','p/B'),source(4,'p/B','p/A'),
                 source(5,'p/Final',flags=0x11),source(6,'p/Invalid','p/Final')]
        self.assertEqual(V.source_model(classes)[3],[1,2,3,4,6])

    def test_static_fields_do_not_enter_traced_instance_prefix(self):
        classes=[source(0,'java/lang/Object',''),source(1,'p/F',fields=[('global','Ljava/lang/Object;',9),('b','B',1)])]
        _,_,parents,omitted=V.source_model(classes);self.assertEqual(omitted,[])
        fields,payload,refs=V.physical_fields(classes,parents,1)
        self.assertEqual(([f['name'] for f in fields],payload,refs),(['b'],1,0))


if __name__=='__main__':unittest.main()
