"""Native registration must retain exact original fields and reference bounds."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('file_bootstrap_source_tests',ROOT/'scripts/file-bootstrap-source.py')
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)


class Checks:
    @staticmethod
    def check(value,message):
        if not value:raise ValueError(message)


class FileBootstrapSourceTests(unittest.TestCase):
    def fixture(self):
        member=dict(name='fd',descriptor='Ljava/io/FileDescriptor;',access=0x12)
        c=dict(id=5,origin=dict(sha256='source'),fields=[member])
        layout=dict(source_sha256='source',diagnostic=None,candidate=dict(payload_bytes=8,reference_prefix=1,
            fields=[dict(member=dict(owner=5,index=0,**member),offset=0,storage_bytes=8,reference=True)]))
        return c,layout,[('fd','Ljava/io/FileDescriptor;',0x12,8,True)]

    def test_rejects_a_field_from_another_declaration(self):
        c,l,s=self.fixture();l['candidate']['fields'][0]['member']['owner']=6
        with self.assertRaisesRegex(ValueError,'normal layout'):M.fields(c,l,s,Checks)

    def test_rejects_reference_outside_the_live_prefix(self):
        c,l,s=self.fixture();l['candidate']['reference_prefix']=0
        with self.assertRaisesRegex(ValueError,'bounds'):M.fields(c,l,s,Checks)

    def test_rejects_missing_private_final_source_contract(self):
        c,l,s=self.fixture();c['fields'][0]['access']=2
        with self.assertRaisesRegex(ValueError,'declaration'):M.fields(c,l,s,Checks)


if __name__=='__main__':unittest.main()
