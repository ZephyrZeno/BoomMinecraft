"""A JCLS data-root derivation must retain every full parent validation result."""
import copy
import importlib.util
from pathlib import Path
import unittest


spec=importlib.util.spec_from_file_location('boot_unnamed_batch_receipt',
    Path(__file__).resolve().parents[1]/'scripts/refresh-boot-unnamed-batch.py')
R=importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


class BootUnnamedFullReceiptTests(unittest.TestCase):
    def setUp(self):
        self.scope={'scope':'parent_verified_batch_plus_one_JCLS_unit'}
        self.parent=dict(verified=True,counts={'assembly_emitted':498179},
            class_literals={'verified':True,'provided_types':109803},frames={'verified':True},
            unsafe_memory={'verified':True},properties={'verified':True},game_started=False,
            sparse_original_vm_image_home={'vm_image_home':'original'})
        self.receipt={k:copy.deepcopy(v) for k,v in self.parent.items() if k!='sparse_original_vm_image_home'}
        self.receipt['bootstrap_unnamed_derivation']=copy.deepcopy(self.scope)

    def test_only_legacy_vm_home_annotation_is_replaced(self):
        R.check_full_receipt(self.receipt,self.parent,self.scope)
        wrong=copy.deepcopy(self.receipt)
        wrong['sparse_original_vm_image_home']=self.parent['sparse_original_vm_image_home']
        with self.assertRaises(ValueError):R.check_full_receipt(wrong,self.parent,self.scope)

    def test_missing_or_failed_child_proofs_are_rejected(self):
        for child in ('frames','unsafe_memory','properties','class_literals'):
            for delete in (True,False):
                wrong=copy.deepcopy(self.receipt)
                if delete:del wrong[child]
                else:wrong[child]['verified']=False
                with self.subTest(child=child,delete=delete),self.assertRaises(ValueError):
                    R.check_full_receipt(wrong,self.parent,self.scope)

    def test_changed_coverage_source_scope_and_execution_claim_are_rejected(self):
        changes=[('counts',{'assembly_emitted':498178}),('bootstrap_unnamed_derivation',{}),
                 ('game_started',True),('extra_proof',{'verified':True})]
        for key,value in changes:
            wrong=dict(self.receipt,**{key:value})
            with self.subTest(key=key),self.assertRaises(ValueError):
                R.check_full_receipt(wrong,self.parent,self.scope)


if __name__=='__main__':unittest.main()
