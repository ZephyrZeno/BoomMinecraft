"""Source signatures and legacy-family root rejection for the two new providers."""
import importlib.util
import json
from pathlib import Path
import unittest
from uuid import uuid4


ROOT=Path(__file__).resolve().parents[1]


def module(name):
    spec=importlib.util.spec_from_file_location('registration_'+name,ROOT/'scripts'/(name+'.py'))
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


S=module('runtime-provider-source');F=module('framed-runtime-service');V=module('verify-runtime-provider-pack')


class NativeRegistration(unittest.TestCase):
    def test_exact_original_IO_and_Parker_source_signatures_are_registered(self):
        registry=S.read(ROOT/'native-config/runtime-providers.json')['families']
        for family,file,access in [('normal-file-input-readonly-v1','file-input-source',0x102),
                                   ('normal-unsafe-park-v1','unsafe-park-source',0x101)]:
            model=module(file);rule=registry[family]
            self.assertEqual((rule['owner'],rule['loader'],rule['source_id']),(model.OWNER,'bootstrap','jdk:java.base'))
            self.assertEqual((rule['pool'],rule['service']),(model.POOL,model.SERVICE))
            expected=[(*spec,access,index) for index,spec in enumerate(model.SPECS)]
            actual=[(m.get('owner',rule['owner']),m['name'],m['descriptor'],m['access'],m['operation']) for m in rule['methods']]
            self.assertEqual(actual,expected)
            self.assertEqual(F.FAMILIES[family][0],file+'.py')

    def test_FD_close_is_distinct_from_FIS_and_the_existing_bootstrap(self):
        registry=S.read(ROOT/'native-config/runtime-providers.json')['families']
        methods=registry['normal-file-input-readonly-v1']['methods']
        self.assertEqual((methods[-1]['owner'],methods[-1]['name'],methods[-1]['descriptor']),('java/io/FileDescriptor','close0','()V'))
        bootstrap=registry['normal-file-bootstrap-v1']
        self.assertNotIn(('java/io/FileDescriptor','close0','()V'),
            [(m.get('owner',bootstrap['owner']),m['name'],m['descriptor']) for m in bootstrap['methods']])

    def test_all_new_generation_and_physical_verification_sources_are_pinned(self):
        required={'scripts/file-input-source.py','native/providers/file_input_readonly.asm.inc',
            'scripts/unsafe-park-source.py','native/providers/unsafe_park.asm.inc',
            'scripts/provider-native-roots.py','native/kernels/provider_native_root_snapshot.asm.inc'}
        self.assertLessEqual(required,set(S.TOOL_FILES))
        self.assertTrue(all(len(S.tools_identity()[name])==64 for name in required))

    def test_legacy_family_cannot_smuggle_an_unmodeled_native_root(self):
        directory=S.ART/'runtime-providers'/'registration-root-negative'/uuid4().hex;directory.mkdir(parents=True)
        manifest=dict(family='object-identity-v1',native_root_spans=[dict(symbol='boom_fake_roots',count=1,kind='unverified')])
        path=directory/'provider.json';path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'Legacy family cannot declare'):V.verify(path,directory,directory)


if __name__=='__main__':unittest.main()
