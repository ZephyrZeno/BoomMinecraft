import copy
import importlib.util
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location('unsafe_fields_verifier',Path(__file__).resolve().parents[1]/'scripts/verify-batch-unsafe-fields.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)

def classes():
    return [dict(id=0,name='base',origin=dict(sha256='base',loader='application'),fields=[
        dict(name='number',descriptor='I',access=1),dict(name='same',descriptor='J',access=1),dict(name='static',descriptor='I',access=9)]),
        dict(id=1,name='child',origin=dict(sha256='child',loader='application'),fields=[
        dict(name='same',descriptor='Ljava/lang/Object;',access=1),dict(name='名字',descriptor='[I',access=1)])]

class UnsafeFieldsVerifierTests(unittest.TestCase):
    def test_declaring_identity_distinguishes_shadowed_fields(self):
        fields,names,ranges=M.model(classes(),[dict(id=0),dict(id=1),dict(id=3),dict(id=4)],[],4)
        self.assertEqual(ranges,[[0,3],[3,2],[0,0],[0,0]])
        self.assertEqual((fields[1]['id'],fields[3]['id']),(1,3))
        self.assertEqual(fields[1]['name_offset'],fields[3]['name_offset'])
        self.assertNotEqual(fields[1]['class_sha256'],fields[3]['class_sha256'])
        self.assertTrue(fields[4]['reference'])
        at=fields[4]['name_offset'];self.assertEqual(names[at:at+fields[4]['name_units']],list(M.utf16('名字')))

    def test_static_and_unprovided_fields_keep_declaration_but_no_fake_map(self):
        fields,_,_=M.model(classes(),[dict(id=0)],[],2)
        self.assertIsNone(fields[2]['address_map']);self.assertIsNone(fields[1]['address_map'])
        self.assertEqual(fields[1]['storage_bytes'],8)
        with self.assertRaisesRegex(ValueError,'Static declaration'):M.model(classes(),[dict(id=2)],[],2)

    def test_invalid_or_duplicate_address_maps_rejected(self):
        for maps in ([dict(id=99)],[dict(id=0),dict(id=0)]):
            with self.subTest(maps=maps),self.assertRaises(ValueError):M.model(classes(),maps,[],2)
        with self.assertRaises(ValueError):M.model(classes(),[dict(id=0)],[dict(symbol='boom_field_map0')],2)

    def test_original_private_native_and_source_identity_required(self):
        owner=dict(id=2,name=M.OWNER,origin=dict(loader='bootstrap',source_id='jdk:java.base',sha256='unsafe'),access=0x31,method_ids=[7])
        inv={7:(2,'objectFieldOffset1','(Ljava/lang/Class;Ljava/lang/String;)J','unsafe',None,0,0,0,0x102)}
        self.assertEqual(M.source_contract([owner],inv)[1][0]['method'],7)
        for column,value in ((0,3),(3,'changed'),(4,'Code'),(8,0x101)):
            altered=dict(inv);row=list(inv[7]);row[column]=value;altered[7]=tuple(row)
            with self.subTest(column=column),self.assertRaises(ValueError):M.source_contract([owner],altered)
        wrong=copy.deepcopy(owner);wrong['origin']['loader']='application'
        with self.assertRaises(ValueError):M.source_contract([wrong],inv)

    def test_cookie_family_does_not_encode_receiver_byte_offsets(self):
        fields,names,ranges=M.model(classes(),[dict(id=0)],[],2)
        shape=dict(class_id=8,value_offset=0,coder_offset=12)
        parts,unit=M.bodies(fields,names,ranges,2,shape,7)
        combined=''.join(parts)
        self.assertIn('055464C4400000000h',combined)
        self.assertIn('QWORD OFFSET boom_field_map0,0',combined)
        self.assertIn('call boom_class_ensure32',parts[unit])
        self.assertNotIn('boom_s',combined)

    def test_page_directory_covers_boundary_field(self):
        source=classes()[:1];source[0]['fields']=[dict(name='f'+str(i),descriptor='B',access=1) for i in range(1025)]
        fields,names,ranges=M.model(source,[],[],1)
        parts,_=M.bodies(fields,names,ranges,2,dict(class_id=8,value_offset=0,coder_offset=12),7)
        text=''.join(parts)
        self.assertIn('boom_java_unsafe_field_page1 LABEL BYTE',text)
        self.assertEqual(fields[1024]['id'],1024)

if __name__=='__main__':unittest.main()
