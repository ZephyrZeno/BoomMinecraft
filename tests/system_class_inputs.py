"""A faster source container cannot replace locked original class contents."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SPEC=importlib.util.spec_from_file_location('system_class_input_tests',
    Path(__file__).resolve().parents[1]/'scripts/system-class-inputs.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)


class SystemClassInputTests(unittest.TestCase):
    def fixture(self, root, archive_bytes=b'original', image_bytes=b'original'):
        root=Path(root);catalog=root/'catalog/jdk-classes.json';catalog.parent.mkdir()
        image=root/'catalog/image/java.base/java/lang/Object.class';image.parent.mkdir(parents=True)
        if image_bytes is not None:image.write_bytes(image_bytes)
        jmods=root/'jdk/jmods';jmods.mkdir(parents=True)
        if archive_bytes is not None:
            with zipfile.ZipFile(jmods/'java.base.jmod','w') as z:z.writestr('classes/java/lang/Object.class',archive_bytes)
        origin=dict(loader='bootstrap',binary_name='java.lang.Object',source_id='jdk:java.base',
            jar_entry='java.base/java/lang/Object.class',java_class_major=65,sha256=hashlib.sha256(b'original').hexdigest())
        catalog.write_text(json.dumps(dict(image=dict(path=str(root/'jdk/lib/modules')),classes={'java.lang.Object':origin})))
        return catalog,origin

    def test_byte_identical_archive_needs_no_extracted_file(self):
        with tempfile.TemporaryDirectory() as root:
            catalog,origin=self.fixture(root,image_bytes=None);r=M.SystemClasses(catalog)
            try:
                self.assertEqual(r.read(origin),b'original');self.assertEqual((r.archive_hits,r.image_reads),(1,0))
            finally:r.close()

    def test_missing_archive_uses_the_locked_original_image(self):
        with tempfile.TemporaryDirectory() as root:
            catalog,origin=self.fixture(root,archive_bytes=None);r=M.SystemClasses(catalog)
            try:self.assertEqual(r.read(origin),b'original');self.assertEqual((r.archive_hits,r.image_reads),(0,1))
            finally:r.close()

    def test_missing_linked_image_generated_entry_uses_original_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            catalog,origin=self.fixture(root)
            with zipfile.ZipFile(Path(root)/'jdk/jmods/java.base.jmod','w') as z:z.writestr('classes/Other.class',b'other')
            r=M.SystemClasses(catalog)
            try:self.assertEqual(r.read(origin),b'original');self.assertEqual(r.image_reads,1)
            finally:r.close()

    def test_different_installed_archive_cannot_change_the_locked_input(self):
        with tempfile.TemporaryDirectory() as root:
            catalog,origin=self.fixture(root,archive_bytes=b'different');r=M.SystemClasses(catalog)
            try:self.assertEqual(r.read(origin),b'original');self.assertEqual((r.archive_hits,r.image_reads),(0,1))
            finally:r.close()

    def test_changed_archive_and_image_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            catalog,origin=self.fixture(root,archive_bytes=b'different',image_bytes=b'different');r=M.SystemClasses(catalog)
            try:
                with self.assertRaisesRegex(ValueError,'bytes changed'):r.read(origin)
            finally:r.close()

    def test_forged_source_origin_cannot_retarget_the_archive(self):
        with tempfile.TemporaryDirectory() as root:
            catalog,origin=self.fixture(root);r=M.SystemClasses(catalog)
            try:
                for key,value in [('loader','application'),('source_id','jdk:../other'),('jar_entry','../../other.class'),('sha256','forged')]:
                    with self.subTest(key=key),self.assertRaisesRegex(ValueError,'locked catalog'):r.read(dict(origin,**{key:value}))
            finally:r.close()
