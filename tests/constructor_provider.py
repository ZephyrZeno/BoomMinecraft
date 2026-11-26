"""Constructor metadata must preserve Java reflection semantics, not slot widths."""
import importlib.util
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

SPEC=importlib.util.spec_from_file_location('constructor_source_tests',Path(__file__).resolve().parents[1]/'scripts/constructor-provider-source.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)

class ConstructorSourceTests(unittest.TestCase):
    def test_parameters_are_classes_not_jvm_local_slots(self):
        self.assertEqual(M.parameter_names('(JDLjava/lang/String;[[I[Ljava/lang/Object;)V'),
            ['J','D','Ljava/lang/String;','[[I','[Ljava/lang/Object;'])
        self.assertEqual(M.parameter_names('()V'),[])

    def test_void_arrays_and_incomplete_parameters_rejected(self):
        for desc in ('(V)V','([V)V','(Lmissing)V','([)V','(I)I','(Qx;)V'):
            with self.subTest(desc=desc),self.assertRaises(ValueError):M.parameter_names(desc)

    def test_original_attributes_preserve_signature_exceptions_and_raw_annotations(self):
        constants=[]
        def utf(s):
            b=s.encode();constants.append(b'\x01'+struct.pack('>H',len(b))+b);return len(constants)
        def clazz(s):
            n=utf(s);constants.append(b'\x07'+struct.pack('>H',n));return len(constants)
        owner=clazz('fixture/Ctor');parent=clazz('java/lang/Object');name=utf('<init>');desc=utf('(J)V')
        sn=utf('Signature');sv=utf('<T:Ljava/lang/Object;>(J)V');en=utf('Exceptions');ex=clazz('java/io/IOException')
        an=utf('RuntimeVisibleAnnotations');pa=utf('RuntimeVisibleParameterAnnotations');co=utf('Code')
        attrs=[(sn,struct.pack('>H',sv)),(en,struct.pack('>HH',1,ex)),(an,b'\0\0'),(pa,b'\1\0\0'),
               (co,struct.pack('>HHI',0,3,1)+b'\xb1'+b'\0\0\0\0')]
        method=struct.pack('>HHHH',1,name,desc,len(attrs))+b''.join(struct.pack('>HI',n,len(b))+b for n,b in attrs)
        raw=struct.pack('>IHHH',0xcafebabe,0,65,len(constants)+1)+b''.join(constants)
        raw+=struct.pack('>HHHHHH',1,owner,parent,0,0,1)+method+b'\0\0'
        actual,methods=M.methods(raw);self.assertEqual(actual,'fixture/Ctor');m=methods[0]
        self.assertEqual(m['slot'],0);self.assertEqual(m['signature'],'<T:Ljava/lang/Object;>(J)V')
        self.assertEqual(m['exceptions'],['java/io/IOException'])
        self.assertEqual(m['annotations'],'0000');self.assertEqual(m['parameter_annotations'],'010000')
        self.assertEqual(m['type_annotations'],'')

    def test_primitive_resolution_uses_frozen_descriptor_names(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'types.zip'
            rows=[dict(id=i+20,defining_loader='bootstrap',name=n) for i,n in enumerate(('I','J','V','[I'))]
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('types.jsonl','\n'.join(map(json.dumps,rows)));z.writestr('runtime.jsonl','')
            summary=dict(runtime_metadata=dict(index=dict(path=str(path),digest=dict(size=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))))
            classes=[dict(id=0,name='java/lang/Object',origin=dict(loader='bootstrap',source_id='jdk:java.base'),access=1,superclass=None,interfaces=[])]
            _,_,_,resolve=M.inputs(summary,classes)
            self.assertEqual([resolve('bootstrap',n) for n in ('I','J','V','[I')],[20,21,22,23])

if __name__=='__main__':unittest.main()
