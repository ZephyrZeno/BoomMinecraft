"""Keep provider contracts independent of signatures that merely look similar."""
import copy
import importlib.util
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location('provider_contract_tests',Path(__file__).resolve().parents[1]/'scripts/verify-runtime-provider-pack.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)


def source():
    owner=dict(id=7,name='jdk/internal/misc/CDS',origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='a'*64),method_ids=list(range(10,15)))
    methods=[dict(name=n,descriptor=d,access=a,code=None) for n,d,a,_ in M.SPECS]
    return owner,methods


class RuntimeProviderContractTests(unittest.TestCase):
    def test_five_semantic_operations_bind_exact_original_native_ids(self):
        owner,methods=source();result=M.contract([],owner,methods)
        self.assertEqual([r['method'] for r in result],list(range(10,15)))
        self.assertEqual([r['operation'] for r in result],list(range(5)))
        self.assertEqual(result[0]['descriptor'],'(Ljava/lang/Class;)V')

    def test_application_or_transformed_class_cannot_claim_bootstrap_service(self):
        owner,methods=source()
        for change in [dict(loader='application'),dict(source_id='library:spoof'),dict(generated={'host':'CDS'})]:
            bad=copy.deepcopy(owner);bad['origin'].update(change)
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'original bootstrap'):M.contract([],bad,methods)

    def test_java_body_and_changed_access_are_not_native_provider_matches(self):
        owner,methods=source()
        for field,value in [('access',0x10a),('code',(b'\xb1',0,0))]:
            bad=copy.deepcopy(methods);bad[0][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'flags/Code changed'):M.contract([],owner,bad)

    def test_overloads_and_incomplete_inventory_are_not_guessed(self):
        owner,methods=source();methods[0]['descriptor']='(Ljava/lang/Object;)V'
        with self.assertRaisesRegex(ValueError,'declaration missing'):M.contract([],owner,methods)
        with self.assertRaisesRegex(ValueError,'inventory differs'):M.contract([],owner,methods[:-1])

    def test_identity_family_keeps_instance_and_static_source_signatures_distinct(self):
        owners={name:dict(id=i,origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='a'*64),method_ids=[i+10]) for i,name in enumerate(['java/lang/Object','java/lang/System'])}
        raw={'java/lang/Object':[dict(name='hashCode',descriptor='()I',access=0x101,code=None)],
             'java/lang/System':[dict(name='identityHashCode',descriptor='(Ljava/lang/Object;)I',access=0x109,code=None)]}
        result=M.identity_contract(owners,raw)
        self.assertEqual([(r['owner'],r['operation']) for r in result],[('java/lang/Object',0),('java/lang/System',1)])
        raw['java/lang/Object'][0]['access']=0x109
        with self.assertRaisesRegex(ValueError,'native changed'):M.identity_contract(owners,raw)


if __name__=='__main__':unittest.main()
