import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

SPEC=importlib.util.spec_from_file_location('batch_source_selection',Path(__file__).resolve().parents[1]/'scripts/batch-source.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)
SPEC=importlib.util.spec_from_file_location('guarded_source_selection',Path(__file__).resolve().parents[1]/'scripts/prepare-class-init-probe.py')
SELECT=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(SELECT)


class SourceSelectionTests(unittest.TestCase):
    def test_mixed_server_client_or_missing_source_identity_rejects(self):
        for batch,plan in (({'input_fingerprint':'server'},{'input_fingerprint':'client'}),({},{}),({'input_fingerprint':''},{'input_fingerprint':''})):
            with self.subTest(batch=batch,plan=plan),self.assertRaisesRegex(ValueError,'identity differs'):SELECT.source_identity(batch,plan)

    def test_matching_source_identity_is_preserved(self):
        self.assertEqual(SELECT.source_identity({'input_fingerprint':'source'},{'input_fingerprint':'source'}),'source')

    def test_exact_frame_and_leaf_bodies_share_one_index(self):
        source='.code\nboom_m1 PROC FRAME\n ret\nboom_m1 ENDP\n.const\nboom_m2 PROC\n ret\nboom_m2 ENDP\nEND\n'
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'unit.asm';path.write_text(source,encoding='utf-8');cache=M.Sources()
            self.assertEqual(cache.function(path,'boom_m2'),'boom_m2 PROC\n ret\nboom_m2 ENDP\n')
            self.assertEqual(cache.function(path,'boom_m1'),'boom_m1 PROC FRAME\n ret\nboom_m1 ENDP\n')
            self.assertEqual((cache.reads,cache.indexes),(1,1))
            with self.assertRaisesRegex(ValueError,'missing'):cache.function(path,'boom_m3')

    def test_malformed_or_duplicate_boundaries_reject(self):
        for source in ('boom_m1 PROC\n','boom_m1 ENDP\n','boom_m1 PROC\nboom_m2 ENDP\n',
                       'boom_m1 PROC\nboom_m2 PROC\nboom_m2 ENDP\nboom_m1 ENDP\n',
                       'boom_m1 PROC\nboom_m1 ENDP\nboom_m1 PROC\nboom_m1 ENDP\n'):
            with self.subTest(source=source),self.assertRaises(ValueError):M.procedure_spans(source)

    def test_evicted_source_is_read_and_checked_again(self):
        with tempfile.TemporaryDirectory() as root:
            a,b=Path(root)/'a.asm',Path(root)/'b.asm'
            a.write_text('boom_m1 PROC\n ret\nboom_m1 ENDP\n',encoding='utf-8')
            b.write_text('boom_m2 PROC\n ret\nboom_m2 ENDP\n',encoding='utf-8')
            cache=M.Sources(35);cache.function(a,'boom_m1');cache.function(b,'boom_m2')
            a.write_text('boom_m1 PROC\n int 3\nboom_m1 ENDP\n',encoding='utf-8')
            self.assertIn(' int 3\n',cache.function(a,'boom_m1'))
            self.assertEqual((cache.reads,cache.indexes),(3,3))

    def test_function_index_survives_text_eviction(self):
        with tempfile.TemporaryDirectory() as root:
            a,b=Path(root)/'a.asm',Path(root)/'b.asm'
            for path,id_ in ((a,1),(b,2)):path.write_text(f'boom_m{id_} PROC\n ret\nboom_m{id_} ENDP\n',encoding='utf-8')
            cache=M.Sources(35);cache.text(a);first=cache.function(a,'boom_m1');cache.text(b)
            self.assertNotIn(str(a),cache.entries)
            self.assertEqual(cache.function(a,'boom_m1'),first)
            self.assertEqual((cache.indexes,cache.slices),(1,2))

    def test_binary_ranges_preserve_unicode_and_normalize_CRLF(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'unit.asm';path.write_bytes('; 中文\r\nboom_m1 PROC\r\n ; 原文\r\n ret\r\nboom_m1 ENDP\r\n'.encode('utf-8'))
            self.assertEqual(M.Sources().function(path,'boom_m1'),'boom_m1 PROC\n ; 原文\n ret\nboom_m1 ENDP\n')

    def test_exact_class_descriptor_ranges_and_duplicate_rejection(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'state.asm';body='boom_class12 DWORD 0434C4153h,2,0,0\n QWORD OFFSET boom_batch_initialize_12\n DWORD 12,0\n QWORD 0,0,0,OFFSET boom_batch_class_failure_root12\n'
            path.write_bytes(('; 中文\n'+body).replace('\n','\r\n').encode('utf-8'));cache=M.Sources()
            self.assertEqual(cache.class_descriptor(path,12),body)
            with self.assertRaisesRegex(ValueError,'missing'):cache.class_descriptor(path,13)
            path.write_text(body+body,encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Duplicate'):cache.class_descriptor(path,12)

    def test_dispatch_fragments_keep_complete_boundaries_and_original_data(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'dispatch.asm';name='boom_batch_vconstraints_boom_batch_call_1_2_182'
            body=f'.const\nALIGN 8\n{name} QWORD OFFSET boom_t4,OFFSET boom_t5\n'
            path.write_text(body+'.code\n',encoding='utf-8');cache=M.Sources()
            self.assertEqual(cache.fragment(path,name,body),body)
            with self.assertRaisesRegex(ValueError,'differs'):cache.fragment(path,name,body.replace('boom_t5','boom_t6'))
            path.write_text(body+body,encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Duplicate'):cache.fragment(path,name,body)

    def test_exception_handlers_are_copied_with_complete_source_rows(self):
        table='.const\nALIGN 8\nboom_handlers7 DWORD 045584348h, 1, 1, 0\n    QWORD OFFSET boom_handler_rows7, OFFSET boom_runtime_type_map, OFFSET boom_t3\nboom_handler_rows7 LABEL BYTE\n    DWORD 0, 4, 8, 0\n    QWORD 0\n'
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'handlers.asm';p.write_bytes((table+'.code\n').replace('\n','\r\n').encode('utf-8'));cache=M.Sources()
            self.assertEqual(cache.handler_table(p,7),table)
            with self.assertRaisesRegex(ValueError,'Missing'):cache.handler_table(p,8)
            previous_stamp=p.stat().st_mtime_ns
            p.write_text(table.replace('1, 1, 0','1, 2, 0')+'.code\n',encoding='utf-8')
            # Same-length writes can share a filesystem timestamp tick on Windows.
            os.utime(p,ns=(p.stat().st_atime_ns,previous_stamp+1_000_000_000))
            with self.assertRaisesRegex(ValueError,'invalid'):cache.handler_table(p,7)

    def test_dispatch_index_checks_every_receiver_row(self):
        table=('.const\nALIGN 8\nPUBLIC boom_batch_vtable7\n'
            'boom_batch_vtable7 DWORD 056445350h,1,2,0\n QWORD OFFSET boom_batch_vrows7,0\n'
            ' DWORD 1,0\nboom_batch_vrows7 LABEL BYTE\n'
            ' DWORD 3,0\n QWORD OFFSET boom_m9\n DWORD 4,0\n QWORD OFFSET boom_m10\n')
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'dispatch.asm';p.write_text(table+'.code\n',encoding='utf-8')
            self.assertEqual(M.Sources().fragment(p,'boom_batch_vtable7',table),table)
            p.write_text(table.replace('boom_m10','boom_m11')+'.code\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'differs'):M.Sources().fragment(p,'boom_batch_vtable7',table)

    def test_dispatch_index_rejects_duplicate_symbol_with_different_contents(self):
        name='boom_batch_vconstraints_boom_batch_call_1_2_182'
        table=f'.const\nALIGN 8\n{name} QWORD OFFSET boom_t4,OFFSET boom_t5\n'
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'dispatch.asm';p.write_text(table+table.replace('boom_t5','boom_t6')+'.code\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Duplicate'):M.Sources().fragment(p,name,table)

    def test_handler_index_rejects_duplicate_identity_with_different_rows(self):
        table=('.const\nALIGN 8\nboom_handlers7 DWORD 045584348h, 1, 1, 0\n'
            '    QWORD OFFSET boom_handler_rows7, OFFSET boom_runtime_type_map, OFFSET boom_t3\n'
            'boom_handler_rows7 LABEL BYTE\n    DWORD 0, 4, 8, 0\n    QWORD 0\n')
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'handlers.asm';p.write_text(table+'.code\n'+table.replace('0, 4, 8','0, 4, 9')+'.code\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Duplicate'):M.Sources().handler_table(p,7)

    def test_handler_index_accepts_adjacent_closure_tables_without_code_sections(self):
        table=('.const\nALIGN 8\nboom_handlers7 DWORD 045584348h, 1, 1, 0\n'
            '    QWORD OFFSET boom_handler_rows7, OFFSET boom_runtime_type_map, OFFSET boom_t3\n'
            'boom_handler_rows7 LABEL BYTE\n    DWORD 0, 4, 8, 0\n    QWORD 0\n')
        second=table.replace('handlers7','handlers8').replace('rows7','rows8')
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'closure.asm';p.write_bytes((table+'\n'+second+'\n.code\n').replace('\n','\r\n').encode())
            cache=M.Sources();self.assertEqual(cache.handler_table(p,7),table);self.assertEqual(cache.handler_table(p,8),second)
            self.assertEqual(cache.metadata_indexes,1)

if __name__=='__main__':unittest.main()
