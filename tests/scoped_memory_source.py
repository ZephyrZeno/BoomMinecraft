"""Registration must preserve the original foreign-close contract and its gap."""
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]


def load(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


M=load('scoped_source_tests','scoped-memory-source.py');S=load('scoped_source_test_io','runtime-provider-source.py')


class ScopedMemorySourceTests(unittest.TestCase):
    def fixture(self):
        c=dict(id=0,name=M.OWNER,access=0x21,method_ids=[12,13],origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='original'))
        methods=[dict(name=n,descriptor=d,access=a,code=None) for n,d,a in M.SPECS]
        return c,methods

    def index(self,c,methods):
        with mock.patch.object(S,'original_class',return_value=b'original'),mock.patch.object(M.R,'original_methods',return_value=(M.OWNER,methods)):
            return M.index({},[c],S)

    def test_registration_does_not_claim_close_handshake(self):
        c,methods=self.fixture();m=self.index(c,methods)
        self.assertEqual((m['registration']['method'],m['unavailable_close']['method'],m['registered_entries']),(12,13,1))
        self.assertFalse(m['close_scope_implemented']);self.assertFalse(m['thread_handshake_implemented'])

    def test_rejects_changed_close_descriptor(self):
        c,methods=self.fixture();methods[1]['descriptor']='(Ljava/lang/Object;)Z'
        with self.assertRaisesRegex(ValueError,'closeScope0'):self.index(c,methods)

    def test_rejects_changed_close_access_or_Code(self):
        for field,value in [('access',0x101),('code',b'\xb1')]:
            c,methods=self.fixture();methods[1][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'closeScope0'):self.index(c,methods)

    def test_rejects_added_native(self):
        c,methods=self.fixture();c['method_ids'].append(14);methods.append(dict(name='extra',descriptor='()V',access=0x10a,code=None))
        with self.assertRaisesRegex(ValueError,'native inventory'):self.index(c,methods)

    def test_rejects_generated_bootstrap_owner(self):
        c,methods=self.fixture();c['origin']['generated']={'kind':'transformed'}
        with self.assertRaisesRegex(ValueError,'original bootstrap'):self.index(c,methods)


if __name__=='__main__':unittest.main()
