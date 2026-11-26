"""Read locked JDK class bytes, using JMODs only as byte-identical input copies.

This is an offline file reader. Every returned class still matches its locked
catalog SHA256; linked-image-only classes use the original extracted image.
"""
import hashlib
import json
from pathlib import Path
import zipfile


class SystemClasses:
    def __init__(self, catalog_path):
        self.catalog_path = Path(catalog_path).resolve()
        self.catalog = json.loads(self.catalog_path.read_text(encoding='utf-8'))
        self.image = (self.catalog_path.parent/'image').resolve()
        self.jmods = (Path(self.catalog['image']['path']).parent.parent/'jmods').resolve()
        self.archives = {}
        self.archive_hits = self.image_reads = 0

    def close(self):
        for archive in self.archives.values():
            if archive is not None:
                archive.close()
        self.archives.clear()

    def read(self, origin):
        locked = self.catalog['classes'].get(origin['binary_name'])
        if locked is None or any(origin.get(k) != locked.get(k) for k in
                ('loader','binary_name','source_id','jar_entry','java_class_major','sha256')):
            raise ValueError('System class source differs from its locked catalog')
        module = origin['source_id'].removeprefix('jdk:')
        entry = origin['jar_entry']
        if not origin['source_id'].startswith('jdk:') or not entry.startswith(module+'/'):
            raise ValueError('Invalid original system class module/entry')
        if module not in self.archives:
            path = (self.jmods/(module+'.jmod')).resolve()
            if not path.is_relative_to(self.jmods):
                raise ValueError('System class input archive escaped the JDK directory')
            try:
                self.archives[module] = zipfile.ZipFile(path)
            except (OSError,zipfile.BadZipFile):
                self.archives[module] = None
        archive = self.archives[module]
        if archive is not None:
            try:
                data = archive.read('classes/'+entry[len(module)+1:])
            except (KeyError,OSError,zipfile.BadZipFile):
                data = None
            if data is not None and hashlib.sha256(data).hexdigest() == origin['sha256']:
                self.archive_hits += 1
                return data
        # A JMOD is merely an optional byte-identical copy. Missing generated
        # species or a different installed JDK must not change the locked input.
        path = (self.image/entry).resolve()
        if not path.is_relative_to(self.image):
            raise ValueError('Original system class escaped the extracted image')
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != origin['sha256']:
            raise ValueError('Original system class bytes changed')
        self.image_reads += 1
        return data
