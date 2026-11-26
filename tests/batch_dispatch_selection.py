import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SPEC=importlib.util.spec_from_file_location('batch_dispatch_selection',Path(__file__).resolve().parents[1]/'scripts/select-batch-dispatch.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)
SPEC=importlib.util.spec_from_file_location('dispatch_source_reader',Path(__file__).resolve().parents[1]/'scripts/batch-source.py')
S=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(S)


class DispatchSelectionTests(unittest.TestCase):
    def table(self):return dict(id=3,rows=[dict(receiver=7,error=0,target=0),dict(receiver=8,error=13,target=None)],array_target=0,array_error=0,diagnostic=None,assembly_unit=0)
    def site(self):return dict(label='boom_batch_call_1_2_182',table=3,dispatch=dict(symbolic_owner=4,receiver_constraint=5),diagnostic=None,assembly_unit=0)
    def bundle(self,path,sites,tables):
        with zipfile.ZipFile(path,'w') as z:
            for name,rows in (('sites.jsonl',sites),('tables.jsonl',tables)):z.writestr(name,''.join(json.dumps(r)+'\n' for r in rows))
        return dict(index=dict(path=str(path)),units=[dict(assembly=dict(path='unit.asm'))])

    def test_zero_method_target_array_target_and_error_rows_preserved(self):
        body=M.table_source(self.table())
        self.assertIn('QWORD OFFSET boom_batch_vrows3,OFFSET boom_m0\n',body)
        self.assertIn(' DWORD 7,0\n QWORD OFFSET boom_m0\n DWORD 8,13\n QWORD 0\n',body)
        self.assertIn(' DWORD 056445350h,1,2,0\n',body)

    def test_protected_receiver_constraint_remains_distinct(self):
        self.assertIn(' QWORD OFFSET boom_t4,OFFSET boom_t5\n',M.constraint_source(self.site()))

    def test_whole_source_rows_selected_and_changed_MASM_rejects(self):
        with tempfile.TemporaryDirectory() as root:
            table=self.table();body=M.table_source(table)
            summary=self.bundle(Path(root)/'index.zip',[self.site()],[table])
            unit=Path(root)/'unit.asm';unit.write_text(body,encoding='utf-8');summary['units'][0]['assembly']['path']=str(unit)
            selector=M.Dispatch(summary,S.Sources())
            self.assertEqual(selector.table(selector.site(self.site()['label'])['table']),table)
            self.assertEqual(selector.fragment(table,body),body)
            with self.assertRaisesRegex(ValueError,'differs'):selector.fragment(table,body.replace('DWORD 7,0','DWORD 7,13'))

    def test_duplicate_and_unavailable_index_entries_reject(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'index.zip';site=self.site();table=self.table()
            summary=self.bundle(path,[site,site],[table])
            with self.assertRaisesRegex(ValueError,'Duplicate'):M.Dispatch(summary,None).load()
            summary=self.bundle(path,[dict(site,diagnostic='unsupported')],[dict(table,diagnostic='invalid hierarchy')])
            selector=M.Dispatch(summary,None)
            with self.assertRaisesRegex(ValueError,'unavailable'):selector.site(site['label'])
            with self.assertRaisesRegex(ValueError,'unavailable'):selector.table(3)
            with self.assertRaisesRegex(ValueError,'absent'):selector.table(4)

if __name__=='__main__':unittest.main()
