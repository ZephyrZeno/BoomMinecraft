import importlib.util
from pathlib import Path
import unittest

S=importlib.util.spec_from_file_location('bitcast_verifier',Path(__file__).resolve().parents[1]/'scripts/verify-batch-bitcasts.py');M=importlib.util.module_from_spec(S);S.loader.exec_module(M)


def inputs():
    classes=[dict(id=1,name='java/lang/Float',access=0x31,origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='float'),method_ids=[10,11,14]),
             dict(id=2,name='java/lang/Double',access=0x31,origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='double'),method_ids=[12,13,15])]
    inv={}
    for i,(owner,n,d,op) in enumerate(M.SPECS,10):
        c=classes[0 if owner.endswith('Float') else 1];inv[i]=(c['id'],n,d,c['origin']['sha256'],None,0,0,0,0x109)
    inv[14]=(1,'floatToIntBits','(F)I','float','java-code',0,0,0,9)
    inv[15]=(2,'doubleToLongBits','(D)J','double','java-code',0,0,0,9)
    return classes,inv


class BitcastVerifierTests(unittest.TestCase):
    def test_only_original_raw_natives_are_provided(self):
        methods,owners=M.source_contract(*inputs());self.assertEqual(owners,[1,2]);self.assertEqual([m['method'] for m in methods],[10,11,12,13])

    def test_native_access_owner_and_absence_of_code_checked(self):
        for col,v in [(0,2),(3,'other'),(4,'unexpected Code'),(8,0x101)]:
            a=inputs();r=list(a[1][10]);r[col]=v;a[1][10]=tuple(r)
            with self.subTest(col=col),self.assertRaises(ValueError):M.source_contract(*a)

    def test_numeric_class_finality_is_required(self):
        a=inputs();a[0][0]['access']=0x21
        with self.assertRaises(ValueError):M.source_contract(*a)

    def test_wrong_loader_source_or_generated_class_rejected(self):
        for key,v in [('loader','application'),('source_id','application'),('generated',{'host':'x'})]:
            a=inputs();a[0][1]['origin'][key]=v
            with self.subTest(key=key),self.assertRaises(ValueError):M.source_contract(*a)

    def test_missing_or_ambiguous_native_rejected(self):
        for change in ('missing','duplicate'):
            a=inputs()
            if change=='missing':a[0][0]['method_ids'].remove(10)
            else:a[0][0]['method_ids'].append(10)
            with self.subTest(change=change),self.assertRaises(ValueError):M.source_contract(*a)

    def test_adapter_preserves_source_init_and_does_not_supply_canonical_java(self):
        b=M.body(10,1,0);self.assertIn('call boom_class_ensure32',b);self.assertIn('jmp boom_java_bitcast',b);self.assertNotIn('7FC00000',b)


if __name__=='__main__':unittest.main()
