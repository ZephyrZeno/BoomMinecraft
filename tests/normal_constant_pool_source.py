"""Classfile CP/readonly COFF boundary fixtures; no guest execution claims."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import unittest
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cp_source_test',ROOT/'scripts/normal-constant-pool-candidate.py')
B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B);N=B.C


def fixture(extra=()):
    entries=[];index=1;ids=[]
    for tag,value in [(1,b'CPParserFixture'),(7,1),(1,b'java/lang/Object'),(7,3),*extra]:
        ids.append(index)
        if tag==1:raw=struct.pack('>H',len(value))+value
        elif tag in (3,4):raw=struct.pack('>I',value)
        elif tag in (5,6):raw=struct.pack('>Q',value)
        elif tag in (7,8,16,19,20):raw=struct.pack('>H',value)
        elif tag in (9,10,11,12,17,18):raw=struct.pack('>HH',*value)
        elif tag==15:raw=struct.pack('>BH',*value)
        else:raw=value
        entries.append(bytes([tag])+raw);index+=2 if tag in (5,6) else 1
    return b'\xca\xfe\xba\xbe\0\0\0A'+struct.pack('>H',index)+b''.join(entries)+struct.pack('>7H',0x21,2,4,0,0,0,0),ids


class CPParserContract(unittest.TestCase):
    def test_original_indices_and_wide_holes(self):
        raw,ids=fixture([(5,0xffffffffffffffff),(6,0x8000000000000000),(3,0x80000001)])
        parsed=N.parse_class_pool(raw)
        self.assertEqual(parsed['name'],'CPParserFixture');self.assertEqual(ids[-3:],[5,7,9])
        self.assertEqual(parsed['entries'][6],(0,-1,None,None));self.assertEqual(parsed['entries'][8],(0,-1,None,None))
        self.assertEqual(len(parsed['entries']),10);self.assertEqual(parsed['entries'][9][2],0x80000001)

    def test_float_double_raw_payloads_are_not_host_numbers(self):
        values=[(4,0x80000000),(4,0x7fc00042),(4,0x7f800000),
                (6,0x7ff8000000000042),(6,0x8000000000000000),(6,0x7ff0000000000000)]
        raw,ids=fixture(values);parsed=N.parse_class_pool(raw)
        for index,(tag,bits) in zip(ids[-len(values):],values):
            self.assertEqual(parsed['entries'][index][0],tag)
            self.assertIs(type(parsed['entries'][index][2]),int)
            self.assertEqual(parsed['entries'][index][2],bits)

    def test_modified_utf8_NUL_BMP_and_surrogate_units(self):
        raw,ids=fixture([(1,b'A\xc0\x80\xe4\xb8\xad\xed\xa0\xbd\xed\xb8\x80')])
        value=N.parse_class_pool(raw)['entries'][ids[-1]][2]
        self.assertEqual(value.encode('utf-16-le','surrogatepass'),bytes.fromhex('410000002d4e3dd800de'))

    def test_four_byte_UTF8_is_not_classfile_modified_utf8(self):
        raw,_=fixture([(1,b'\xf0\x9f\x98\x80')])
        with self.assertRaises(ValueError):N.parse_class_pool(raw)

    def test_reference_must_point_to_correct_original_tag(self):
        for entry in ((7,0),(7,4),(8,4),(12,(1,4)),(10,(1,3))):
            raw,_=fixture([entry])
            with self.subTest(entry=entry),self.assertRaises(ValueError):N.parse_class_pool(raw)

    def test_wide_constant_requires_actual_reserved_slot(self):
        raw,_=fixture([(5,1)]);raw=raw[:8]+struct.pack('>H',6)+raw[10:]
        with self.assertRaises(ValueError):N.parse_class_pool(raw)

    def test_invalid_handle_kind_or_truncated_payload_rejected(self):
        raw,_=fixture([(15,(0,2))])
        with self.assertRaises(ValueError):N.parse_class_pool(raw)
        raw,_=fixture([(1,b'constant')])
        with self.assertRaises(ValueError):N.parse_class_pool(raw[:-18])


class ReadonlyROMContract(unittest.TestCase):
    def setUp(self):
        self.output=ROOT/'.boom/normal-constant-pool/ROM-tests'/uuid4().hex;self.output.mkdir(parents=True)
        self.payload=struct.pack('<6I',0,1,1,0,0,0)+b'\0'*8
        self.meta=dict(readonly_section_bytes=len(self.payload),readonly_section_sha256=hashlib.sha256(self.payload).hexdigest(),
            entry_section_offset=24,raw_section_offset=32)
        self.path=self.output/'ROM.obj';self.path.write_bytes(N.rom_coff(self.payload,self.meta))

    def test_actual_data_COFF_has_no_code_relocations_or_imports(self):
        proof=B.verify_rom_object(self.path,self.meta,self.payload)
        self.assertFalse(proof['code_sections']);self.assertEqual(proof['relocations'],0);self.assertEqual(proof['imports'],[])
        self.assertEqual(proof['sections'],['.rdata'])

    def test_source_byte_change_rejected(self):
        raw=bytearray(self.path.read_bytes());raw[64]^=1;self.path.write_bytes(raw)
        with self.assertRaises(ValueError):B.verify_rom_object(self.path,self.meta,self.payload)

    def test_writable_or_executable_section_flags_rejected(self):
        baseline=self.path.read_bytes()
        for flags in (0xc0500040,0x60500020):
            raw=bytearray(baseline);struct.pack_into('<I',raw,56,flags);self.path.write_bytes(raw)
            with self.subTest(flags=flags),self.assertRaises(ValueError):B.verify_rom_object(self.path,self.meta,self.payload)

    def test_source_payload_digest_cannot_be_self_inconsistent(self):
        with self.assertRaises(ValueError):N.rom_coff(self.payload+b'\0',self.meta)


class BoundedClassResolution(unittest.TestCase):
    def setUp(self):
        self.classes=[dict(name=name,access=access) for name,access in
            [('p/Owner',1),('q/Public',1),('p/Private',0),('q/Private',0),('q/OtherModule',1),('p/OtherLoader',1)]]
        self.jcls={i:dict(module=1 if i==4 else 0,loader=1 if i==5 else 0) for i in range(10)}
        self.types={i:dict(kind=1) for i in range(6)}
        self.types.update({6:dict(kind=3,parent_component=1),7:dict(kind=0),
            8:dict(kind=3,parent_component=7),9:dict(kind=3,parent_component=9)})

    def allowed(self,target,owner=0):
        return N.class_reference_access(owner,target,self.jcls,self.types,self.classes)

    def test_same_module_public_and_same_runtime_package_are_proven(self):
        self.assertTrue(self.allowed(0));self.assertTrue(self.allowed(1));self.assertTrue(self.allowed(2))

    def test_catalogue_presence_does_not_prove_cross_package_module_or_loader_access(self):
        self.assertFalse(self.allowed(3));self.assertFalse(self.allowed(4));self.assertFalse(self.allowed(5))

    def test_arrays_follow_the_ultimate_component_access(self):
        self.assertTrue(self.allowed(6));self.assertTrue(self.allowed(8))
        self.types[6]['parent_component']=3;self.assertFalse(self.allowed(6))

    def test_unknown_incomplete_or_cyclic_catalogues_are_not_success(self):
        self.assertFalse(self.allowed(None));self.assertFalse(self.allowed(1,99));self.assertFalse(self.allowed(9))
        del self.types[6];self.assertFalse(self.allowed(6))


if __name__=='__main__':unittest.main()
