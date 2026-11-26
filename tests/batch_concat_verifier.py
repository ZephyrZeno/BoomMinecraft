"""The independent concat model must reject unsupported source contracts."""
import copy
import importlib.util
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location('concat_verifier',Path(__file__).resolve().parents[1]/'scripts/verify-batch-concat.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)


def source(desc='(I)Ljava/lang/String;',recipe=None,extra=()):
    constants={'1':dict(StringUtf16=[1] if recipe is None else recipe)}
    constants.update({str(i):v for i,v in enumerate(extra,2)})
    return dict(descriptor=desc,name='makeConcatWithConstants',arguments=list(range(1,len(extra)+2)),
                bootstrap=dict(owner=M.OWNER,name='makeConcatWithConstants',descriptor=M.BOOTSTRAPS['makeConcatWithConstants'],reference_kind=6,interface=False)),constants


class ConcatVerifierTests(unittest.TestCase):
    def setUp(self):self.converters={'F':11,'D':12,'Ljava/lang/Object;':13};self.signature=M.parser()
    def expand(self,s,c):return M.expand(s,c,self.converters,self.signature)

    def test_array_reference_and_floating_conversions_keep_original_overloads(self):
        s,c=source('([CFD)Ljava/lang/String;',[1,1,1]);p=self.expand(s,c)
        self.assertEqual([v['method'] for v in p['conversions']],[13,11,12])
        self.assertEqual([v['argument'] for v in p['conversions']],[0,1,2])
        self.assertIn('Ljava/lang/Object;',p['conversions'][0]['descriptor'])

    def test_UTF16_static_markers_are_data_and_not_recursive_recipes(self):
        s,c=source(recipe=[0,0xd800,2,1,0xdc00],extra=[dict(StringUtf16=[1,2])]);p=self.expand(s,c)
        self.assertEqual(p['parts'][0],dict(kind='literal',utf16=[0,0xd800,1,2]))
        self.assertEqual(p['parts'][-1]['utf16'],[0xdc00])

    def test_missing_markers_and_nonstring_static_constants_remain_unsupported(self):
        for s,c in [source(recipe=[]),source(recipe=[1,1]),source(recipe=[1,2],extra=[dict(Int=42)])]:
            with self.assertRaises(ValueError):self.expand(s,c)

    def test_argument_limit_counts_wide_slots(self):
        for n,ok in [(100,True),(101,False)]:
            s,c=source('('+'J'*n+')Ljava/lang/String;',[1]*n)
            if ok:self.assertEqual(len(self.expand(s,c)['arguments']),n)
            else:
                with self.assertRaises(ValueError):self.expand(s,c)

    def test_exact_handle_kind_and_signature_are_required(self):
        for field,value in [('owner','mods/StringConcatFactory'),('reference_kind',5),('interface',True),('descriptor','()V')]:
            s,c=source();s['bootstrap'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.expand(s,c)

    def test_generated_body_preserves_initialization_and_error_edges(self):
        s,c=source('(DF)Ljava/lang/String;',[1,1]);p=self.expand(s,c)
        shape=dict(class_id=7,value_offset=0,coder_offset=12,hash_offset=8,hash_is_zero_offset=13)
        b=M.body('boom_batch_call_1_2_186',p,99,shape)
        self.assertLess(b.index('call boom_class_ensure32'),b.index('call boom_m12'))
        self.assertLess(b.index('call boom_m12'),b.index('call boom_m11'))
        self.assertLess(b.index('call boom_m11'),b.index('call boom_java_concat'))
        self.assertIn('mov DWORD PTR [rcx],7',b)
        self.assertNotIn('boom_string_concat',b)


if __name__=='__main__':unittest.main()
